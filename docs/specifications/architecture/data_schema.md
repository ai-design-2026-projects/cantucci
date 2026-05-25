# Data Model

PostgreSQL schema for the conversational clustering system.
We distinguish three logical groups:
- **catalogue tables** — ingested once from the dataset, read-only during session runtime.
- **conversation tables** — written at runtime to capture the evolving state of each conversation.
- **clustering tables** — the content-addressed snapshot tree, its clusters, and soft memberships.

Extensions required: `vector` (pgvector, for `VECTOR` columns), `pgcrypto` (for `gen_random_uuid()`),
and `pg_trgm` (trigram indexing). See `db/migrations/001_extensions.sql`.

The authoritative source is the numbered migrations under `db/migrations/`; this document is the
effective final shape after migrations 001–011.

---

## Catalogue tables

Populated once at ingest time by `db/ingest.py`, which loads the HuggingFace-hosted embedded
parquet (produced by `dataset/scraper.py` → `notebooks/embed_in_colab.ipynb`) into the schema
below. Read-only during the conversational loop.

### `movies`

Primary entity. One row per film. Defined in `db/migrations/003_catalogue.sql`; the
`trailer_embedding` index is added in `010_trailer_embedding_index.sql`.

```sql
CREATE TABLE movies (
    id                  INTEGER PRIMARY KEY,          -- TMDB integer ID
    title               TEXT    NOT NULL,
    original_title      TEXT,
    release_year        INTEGER,
    runtime             FLOAT,                         -- minutes
    vote_average        FLOAT,
    vote_count          INTEGER,
    bayesian_rating     FLOAT,                         -- (v*R + m*C)/(v+m) computed at ingest
    overview            TEXT,                          -- synopsis
    tagline             TEXT,
    poster_path         TEXT,                          -- relative; prepend TMDB base URL at serve time
    original_language   TEXT,                          -- ISO 639-1
    composite_text      TEXT,                          -- concatenated fields embedded as text_embedding
    reviews_text        TEXT,                          -- concatenated reviews embedded as review_embedding
    text_embedding      VECTOR(1024),                  -- BAAI/bge-large-en-v1.5 on composite_text
    review_embedding    VECTOR(1024),                  -- BGE on reviews_text; NULL when no reviews
    trailer_youtube_key TEXT,                          -- YouTube key of the official trailer, or NULL
    trailer_embedding   VECTOR(1024),                  -- mean-pooled CLIP over trailer frames; NULL when absent
    umap_x              FLOAT,                          -- 2D UMAP projection for scatter visualisation
    umap_y              FLOAT
);

CREATE INDEX movies_text_embedding_idx
    ON movies USING ivfflat (text_embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX movies_review_embedding_idx
    ON movies USING ivfflat (review_embedding vector_cosine_ops) WITH (lists = 100)
    WHERE review_embedding IS NOT NULL;

CREATE INDEX movies_trailer_embedding_idx
    ON movies USING ivfflat (trailer_embedding vector_cosine_ops) WITH (lists = 100)
    WHERE trailer_embedding IS NOT NULL;
```

`bayesian_rating` uses `(v * R + m * C) / (v + m)` where `v = vote_count`, `R = vote_average`,
`m` = minimum vote threshold, `C` = global mean. Use this as the ranking signal; raw
`vote_average` should not be used alone.

Each movie carries **three embedding modalities**, matching the `Modality` enum used at runtime
(`backend/agents/clustering/types.py`):

- `text_embedding` — always present; the fused/text BGE embedding over `composite_text`.
- `review_embedding` — present when reviews were available.
- `trailer_embedding` — present when a trailer was fetched and frame-encoded via CLIP.

The review and trailer indexes are **partial** (`WHERE … IS NOT NULL`) so the many rows without
that modality are not indexed.

`composite_text` concatenates the most salient attributes for clustering, e.g.:

```
{title} {original_title} {overview} {tagline} {genres} {top3_cast} {director}
```

---

### `genres`, `people`, `keywords`

Simple lookup tables with `SERIAL` primary keys.

```sql
CREATE TABLE genres (
    id   SERIAL PRIMARY KEY,
    name TEXT   NOT NULL UNIQUE
);

CREATE TABLE people (
    id   SERIAL PRIMARY KEY,
    name TEXT   NOT NULL
);

CREATE TABLE keywords (
    id   SERIAL PRIMARY KEY,
    name TEXT   NOT NULL UNIQUE
);
```

---

### Catalogue join tables

Many-to-many relationships between movies and the lookup tables above.

```sql
CREATE TABLE movie_genres (
    movie_id  INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    genre_id  INTEGER NOT NULL REFERENCES genres (id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, genre_id)
);

CREATE TABLE cast_members (
    movie_id   INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    person_id  INTEGER NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    cast_order INTEGER,                       -- billing order; 0 = top-billed
    PRIMARY KEY (movie_id, person_id)
);

CREATE TABLE crew_members (
    movie_id  INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    job       TEXT    NOT NULL,               -- frequent filter: job = 'Director'
    PRIMARY KEY (movie_id, person_id, job)
);

CREATE TABLE movie_keywords (
    movie_id   INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    keyword_id INTEGER NOT NULL REFERENCES keywords (id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, keyword_id)
);
```

Production companies, spoken languages, and countries are fetched from TMDB but are **not**
persisted as normalised tables in the current schema; only the genre, cast, crew, and keyword
relationships are stored.

---

## Auth tables

Defined in `db/migrations/002_users.sql`.

```sql
CREATE TABLE roles (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE        -- 'user' | 'admin'
);

INSERT INTO roles (name) VALUES ('user'), ('admin');

CREATE TABLE users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,
    role_id       INTEGER     NOT NULL REFERENCES roles (id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

The register endpoint always creates `role = user`. The `roles` table seeds both `user` and
`admin`, but no HTTP route checks for `admin` in the current backend.

---

## Run table

Defined in `db/migrations/004_runs.sql`. Minimal: it stores the YAML config snapshot and its hash
so a clustering run can be reproduced and so cluster snapshots can be content-addressed against the
config that produced them.

```sql
CREATE TABLE runs (
    run_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    config_hash     TEXT        NOT NULL,    -- SHA-256 prefix from backend.settings.get_config_hash()
    config_snapshot JSONB       NOT NULL,    -- full YAML config for replay
    seed            INTEGER     NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Conversation tables

Written at runtime by the conversational loop. A `uuid` is generated for each conversation and
message to serve as stable identifiers. Defined in `db/migrations/005_conversations.sql`;
cost-tracking columns added in `011_message_and_conversation_costs.sql`.

### `conversations`

One row per conversation. `current_cluster_snapshot_id` points at the snapshot the conversation is
currently viewing (NULL = unclustered state). `config_snapshot` records the active config at
creation time. `accumulated_cost_usd` is the running total LLM spend across all turns.

```sql
CREATE TABLE conversations (
    id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     UUID        REFERENCES users (id) ON DELETE SET NULL,  -- NULL for anonymous
    current_cluster_snapshot_id UUID,                                                   -- active snapshot pointer
    config_snapshot             JSONB       NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accumulated_cost_usd        FLOAT       NOT NULL DEFAULT 0.0    -- added in migration 011
);
```

The per-conversation cost limit lives in the YAML config (`backend/settings.py`), not in the DB.

### `messages`

One row per message. `role` is constrained to `user` or `assistant`. `cost_usd` is the LLM cost
attributed to producing that message (0 for user messages).

```sql
CREATE TABLE messages (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cost_usd        FLOAT       NOT NULL DEFAULT 0.0    -- added in migration 011
);

CREATE INDEX messages_conversation_id_idx ON messages (conversation_id);
```

---

## Clustering tables

The clustering state is a **content-addressed tree of snapshots**. Each navigation operation
(drill-down, merge, focus, cross-filter) produces a new `cluster_snapshots` row whose parent is the
snapshot it was derived from. Snapshots are reused across conversations via a deterministic cache
key, so the join table `conversation_snapshot_refs` records which conversations have touched which
snapshots.

### `cluster_snapshots`

Defined in `db/migrations/006_cluster_snapshots.sql`; `config_hash` added and `conversation_id`
dropped in `009_snapshot_cache.sql`.

```sql
CREATE TABLE cluster_snapshots (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id   UUID        REFERENCES cluster_snapshots (id) ON DELETE SET NULL,  -- NULL for root
    operation   TEXT        NOT NULL,        -- 'base' | 'drill_down' | 'merge' | 'focus' | 'cross_filter'
    params      JSONB       NOT NULL DEFAULT '{}',   -- canonicalised operation params for replay
    config_hash TEXT        NOT NULL,        -- config that produced this snapshot (added in 009)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Content-addressed cache key. NULLS NOT DISTINCT so the root snapshot
-- (parent_id IS NULL) is also covered and not duplicated.
CREATE UNIQUE INDEX cluster_snapshots_cache_key_idx
    ON cluster_snapshots (parent_id, operation, params, config_hash) NULLS NOT DISTINCT;
```

Any operation deterministic given `(parent_id, operation, params, config_hash)` is computed once
and reused. `backend/data_access/cluster_snapshots/queries.py:find_cached_snapshot` returns the
existing snapshot on a cache hit, skipping both clustering and LLM labelling.

### `conversation_snapshot_refs`

Join table replacing the old `cluster_snapshots.conversation_id` column. Records which
conversations reference which snapshots so a shared snapshot is not deleted when one referencing
conversation is removed. Added in `db/migrations/009_snapshot_cache.sql`.

```sql
CREATE TABLE conversation_snapshot_refs (
    conversation_id UUID        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    snapshot_id     UUID        NOT NULL REFERENCES cluster_snapshots (id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (conversation_id, snapshot_id)
);

CREATE INDEX conversation_snapshot_refs_snapshot_idx ON conversation_snapshot_refs (snapshot_id);
```

### `clusters`

One row per cluster within a snapshot. `label` is **nullable**: root clusters built at ingest are
persisted without labels and labelled lazily by the labelling agent on first conversation access
(`db/migrations/008_nullable_cluster_label.sql`). `parent_cluster_id` encodes the two-level
hierarchy — a drill-down child references the source cluster it was split from. There is **no**
centroid vector column; cluster shape is defined entirely by its memberships.

```sql
CREATE TABLE clusters (
    id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_snapshot_id UUID    NOT NULL REFERENCES cluster_snapshots (id) ON DELETE CASCADE,
    label               TEXT,                                   -- nullable; lazily labelled (migration 008)
    summary             TEXT,
    exemplar_movie_ids  JSONB   NOT NULL DEFAULT '[]',          -- top movie IDs by probability
    parent_cluster_id   UUID    REFERENCES clusters (id) ON DELETE SET NULL
);
```

### `cluster_memberships`

Soft assignment of a movie to a cluster. Replaces the older hard `cluster_assignments` model — each
row carries a `probability`, and there is no per-row "excluded" flag.

```sql
CREATE TABLE cluster_memberships (
    cluster_id  UUID    NOT NULL REFERENCES clusters (id) ON DELETE CASCADE,
    movie_id    INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    probability FLOAT   NOT NULL,            -- soft-membership probability in (0, 1]
    PRIMARY KEY (cluster_id, movie_id)
);

CREATE INDEX cluster_memberships_cluster_id_idx ON cluster_memberships (cluster_id);
CREATE INDEX cluster_memberships_movie_id_idx   ON cluster_memberships (movie_id);
```

---

## Concept tables

Defined in `db/migrations/007_concepts.sql`. A *concept* is a user-supplied semantic dimension
(e.g. "surrealism") parsed by the concept agent into either a linear axis or a prototype centroid,
then scored against movie embeddings to guide drill-down / cross-filter splits.

```sql
CREATE TABLE concepts (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT        NOT NULL,
    type       TEXT        NOT NULL CHECK (type IN ('linear_axis', 'prototype')),
    definition JSONB       NOT NULL DEFAULT '{}',   -- pole descriptions or exemplar IDs
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE concept_scores (
    concept_id UUID    NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    movie_id   INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    score      FLOAT   NOT NULL,             -- projection of the movie onto the concept
    PRIMARY KEY (concept_id, movie_id)
);

CREATE INDEX concept_scores_concept_id_idx ON concept_scores (concept_id);
```

---

## Entity-relationship summary

```
movies ──► movie_genres    ──► genres
   │
   ├──► cast_members        ──► people
   ├──► crew_members        ──► people
   ├──► movie_keywords      ──► keywords
   ├──► cluster_memberships ◄── clusters
   └──► concept_scores      ◄── concepts

roles ◄── users ──► conversations ──► messages
                          │
                          ├──► conversation_snapshot_refs ──► cluster_snapshots
                          └── current_cluster_snapshot_id ──► cluster_snapshots

cluster_snapshots ──(parent_id, self-ref DAG)──► cluster_snapshots
        └──► clusters ──(parent_cluster_id, self-ref)──► clusters
                  └──► cluster_memberships ──► movies

runs   (config snapshot + hash; referenced by cluster_snapshots.config_hash by value)
```

---

## pgvector notes

- **Dimension**: 1024 (matches `BAAI/bge-large-en-v1.5`) for all three modalities. If the model
  changes via config, the `VECTOR(1024)` columns must be recreated.
- **Modalities**: `text_embedding` (always present, indexed), `review_embedding` and
  `trailer_embedding` (optional, **partial** IVFFlat indexes on `… IS NOT NULL`).
- **Index**: `IVFFlat` with `lists = 100`, tuned for ~45k vectors. Scale `lists` proportionally
  with catalogue size.
- **Similarity**: cosine distance (`vector_cosine_ops`). Query: `ORDER BY embedding <=> $query_vec LIMIT k`.
- **Clusters carry no stored centroid**; the responder agent computes centroids on the fly from
  exemplar embeddings when deriving suggestion signals.
