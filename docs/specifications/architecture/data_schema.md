# Data Model

PostgreSQL schema for the conversational clustering system.
We distinguish four logical groups:
- **catalogue tables** — ingested once from the dataset, read-only during session runtime.
- **auth tables** — user accounts and roles; written by the registration endpoint and the admin CLI.
- **eval harness tables** — runs, personas, ground truths, and per-session results; written by `eval/`, never by the live loop.
- **runtime (session) tables** — conversations, messages, the content-addressed snapshot tree, clusters, memberships, and concepts; written at runtime by the conversational loop.

Extensions required: `vector` (pgvector, for `VECTOR` columns), `pgcrypto` (for `gen_random_uuid()`),
and `pg_trgm` (trigram indexing). See `db/migrations/001_extensions.sql`.

The authoritative source is the numbered migrations under `db/migrations/`; this document is the
effective final shape after migrations 001–017.

`db/apply.py` (the migration runner) maintains a `schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ)` table that records which migration files have been applied. This table is an infrastructure concern and is not part of the domain schema.

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
    bayesian_rating     FLOAT,                         -- (v·R + m·C)/(v+m) computed at ingest
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

`bayesian_rating` is computed at ingest time using the formula:

$$\text{bayesian\_rating} = \frac{v \cdot R + m \cdot C}{v + m}$$

where $v$ = `vote_count`, $R$ = `vote_average`, $m$ = minimum vote threshold, $C$ = global catalogue mean. Use this as the ranking signal; raw `vote_average` should not be used alone.

Each movie carries **three embedding modalities**, matching the `Modality` enum used at runtime
(`backend/agents/intent/types.py`):

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
`admin`. Admin-scoped JWTs are required for all `/eval/*` routes (resolved by `require_admin` in `backend/routers/auth_deps.py`).

---

## Run table

These tables are written by the evaluation harness (`eval/`) to group conversations into experimental runs and store per-conversation results. They are **not** written by the live conversational loop.

### `runs`

Experimental run registry. Extended from migration 004 by migration 012.

```sql
CREATE TABLE runs (
    run_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    config_hash     TEXT        NOT NULL,       -- 8-char SHA-256 prefix of active YAML config
    config_snapshot JSONB       NOT NULL,
    seed            INTEGER     NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    name            TEXT,
    condition       VARCHAR(40) DEFAULT 'conversational',  -- conversational | baseline | human
    model_version   TEXT,
    ended_at        TIMESTAMPTZ,
    status          VARCHAR(40) NOT NULL DEFAULT 'running',  -- running | completed | aborted
    notes           TEXT
);
```

### `personas`

Write-once oracle persona definitions. New behaviour requires a new slug/row.

Each persona YAML bundle (`eval/personas/conf/<slug>.yaml`) is the canonical source. Calling
`eval.personas.store.upsert_bundle` writes **one `personas` row** (carrying `slug`,
`verbosity`, `patience`) and **one `ground_truths` row** (carrying `slug`,
`intent_description`, `operations`, `prompt_hash`) — linked by the shared slug. The
`intent_description`, `operations`, and `prompt_hash` fields from the YAML therefore live in
`ground_truths`, not here.

```sql
CREATE TABLE personas (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug       TEXT        UNIQUE NOT NULL,
    verbosity  TEXT        NOT NULL DEFAULT 'medium',  -- terse | medium | verbose
    patience   FLOAT       NOT NULL DEFAULT 0.5,       -- [0, 1]
    definition JSONB       NOT NULL DEFAULT '{}',      -- currently always {}; reserved for future per-persona config
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `ground_truths`

Ordered trajectory of `(op, concept)` pairs representing the intended navigation path for a simulated session. Built by the GT builder using the judge model tier. `seed_movie_ids` records the catalogue sample used during construction.

`slug` is unique and serves as the stable file-to-DB key: `upsert_bundle` looks up by slug to
detect prompt-hash conflicts and refuse silent overwrites. Since ground-truth rows are always
fetched by `id` (FK from `eval_sessions`) or by `slug` (bundle sync), and the table is small
(one row per bundle), no additional index beyond the PK and the unique slug constraint is needed.

```sql
CREATE TABLE ground_truths (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug               TEXT        UNIQUE NOT NULL,    -- stable key matching the YAML filename
    version            SMALLINT    NOT NULL DEFAULT 1,
    intent_description TEXT        NOT NULL,
    operations         JSONB       NOT NULL,           -- ordered list[{op: str, concept: str, kind?: str, space?: str}]
    seed_movie_ids     JSONB,                          -- nullable; builder audit trail
    prompt_hash        CHAR(64)    NOT NULL,           -- SHA-256 of the GT builder prompts; conflict guard in upsert_bundle
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

```sql
CREATE INDEX ON runs (condition);
CREATE INDEX ON runs (status);
```

**Admin workflow — editing personas by hand.** The YAML files under `eval/personas/conf/` are
the authoritative source; the DB rows are derived from them. At the start of each eval run,
`upsert_bundle` is called for every bundle and syncs the YAML state into `personas` and
`ground_truths`. This means an admin can modify a persona directly by editing the YAML file
(changing `verbosity`, `patience`, `intent_description`, `operations`, etc.) and the DB will
be updated automatically on the next run — no manual SQL required. The only constraint is that
changing the prompt content raises `prompt_hash`, which `upsert_bundle` treats as a conflict
and refuses to overwrite silently; to ship a modified persona the admin must bump the slug
(e.g. `auteur_v2`) so the old row is preserved for replay integrity.

### `eval_sessions`

Links a conversation to a run, persona, and ground truth. `condition` records which experimental arm was run. `oracle_rating` is the 1–5 session-level self-rating emitted by the oracle at stop; NULL for human-oracle sessions.

```sql
CREATE TABLE eval_sessions (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                UUID        NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    conversation_id       UUID        UNIQUE NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    persona_id            UUID        REFERENCES personas (id) ON DELETE SET NULL,
    ground_truth_id       UUID        REFERENCES ground_truths (id) ON DELETE SET NULL,
    seed                  BIGINT      NOT NULL,
    condition             VARCHAR(40) NOT NULL DEFAULT 'conversational',  -- conversational | baseline | human
    status                VARCHAR(40) NOT NULL DEFAULT 'active',          -- active | finished_trajectory | finished_misbehaviour | finished_budget
    termination_rationale TEXT,
    oracle_rating         SMALLINT    CHECK (oracle_rating IS NULL OR oracle_rating BETWEEN 1 AND 5),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON eval_sessions (run_id);
```

### `turn_intents`

Append-only log of the intermediate intent state at each oracle turn. One row per `(conversation, turn, mode)` — the coordinator writes here after intent classification to capture the full internal state of that turn: what mode was detected, which concept was targeted, the confidence score, and whether the clarifier gate fired.

```sql
CREATE TABLE turn_intents (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    turn_number      SMALLINT    NOT NULL,    -- 1-based ordinal
    mode             VARCHAR(40) NOT NULL,    -- any NavigationMode or DialogueMode value
    concept          TEXT,
    target_cluster_id UUID,                   -- not FK'd; snapshots may rotate
    confidence       FLOAT       NOT NULL,
    clarifier_fired  BOOLEAN     NOT NULL DEFAULT FALSE,
    raw_intent       JSONB       NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conversation_id, turn_number, mode)
);

CREATE INDEX ON turn_intents (conversation_id, turn_number);
```

### `conversation_metrics`

Deterministic eval metrics, 1:1 per conversation. Safe to recompute (PK = `conversation_id`, upsert on recompute). `oracle_rating` lives on `eval_sessions` (session-level emission).

```sql
CREATE TABLE conversation_metrics (
    conversation_id       UUID          PRIMARY KEY REFERENCES conversations (id) ON DELETE CASCADE,
    final_num_clusters    SMALLINT,
    clarifier_trigger_rate FLOAT,
    num_turns             SMALLINT      NOT NULL DEFAULT 0,
    num_operations        SMALLINT      NOT NULL DEFAULT 0,
    total_cost_usd        NUMERIC(10,4) NOT NULL DEFAULT 0,
    computed_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
```

### `judge_scores`

LLM-judge dimension scores. Append-only; `judge_prompt_hash` lets multiple judge versions coexist. Dimension values: `operation_appropriateness`, `label_accuracy`, `clustering_coherence`, `suggestion_meaningfulness` (conditional), `explanation_quality` (conditional), `intent_alignment`, `concept_axis_quality` (conditional — only when the session built ≥1 concept axis).

```sql
CREATE TABLE judge_scores (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id   UUID        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    dimension         VARCHAR(40) NOT NULL,  -- operation_appropriateness | label_accuracy | clustering_coherence | suggestion_meaningfulness | explanation_quality | intent_alignment | concept_axis_quality
    score             SMALLINT    NOT NULL CHECK (score BETWEEN 1 AND 5),
    rationale         TEXT,
    judge_model       TEXT        NOT NULL,
    judge_prompt_hash CHAR(64)    NOT NULL,  -- SHA-256 hex of rendered judge prompt
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conversation_id, dimension, judge_prompt_hash)
);

CREATE INDEX ON judge_scores (conversation_id);
CREATE INDEX ON judge_scores (dimension);
```

---

## Runtime (session) tables

Written at runtime by the conversational loop (`backend/coordinator/`) to capture the evolving state of each conversation.

### `conversations`

One row per user conversation. `current_cluster_snapshot_id` is the live pointer to the most recent cluster state.

```sql
CREATE TABLE conversations (
    id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     UUID        REFERENCES users(id) ON DELETE SET NULL,
    current_cluster_snapshot_id UUID,                           -- no FK; snapshot deletions are managed via conversation_snapshot_refs
    config_snapshot             JSONB       NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accumulated_cost_usd        FLOAT       NOT NULL DEFAULT 0.0
);
```

### `messages`

One row per turn (user message or assistant reply).

```sql
CREATE TABLE messages (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cost_usd        FLOAT       NOT NULL DEFAULT 0.0,
    suggestion      TEXT,                       -- proactive next-step suggestion text; NULL when absent
    axis_concept_id UUID        REFERENCES concepts(id) ON DELETE SET NULL  -- linked linear-axis concept; NULL when absent
);

CREATE INDEX ON messages (conversation_id);
```

### `cluster_snapshots`

Content-addressed snapshot tree. Each node is keyed on `(parent_id, operation, params, config_hash)`; identical operations on the same parent are shared across conversations.

```sql
CREATE TABLE cluster_snapshots (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id   UUID        REFERENCES cluster_snapshots(id) ON DELETE SET NULL,
    operation   TEXT        NOT NULL,
    params      JSONB       NOT NULL DEFAULT '{}',
    config_hash TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (parent_id, operation, params, config_hash)
);
```

### `clusters`

Named clusters belonging to a snapshot.

```sql
CREATE TABLE clusters (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_snapshot_id UUID        NOT NULL REFERENCES cluster_snapshots(id) ON DELETE CASCADE,
    label               TEXT,                   -- NULL for unlabelled root clusters; filled lazily
    summary             TEXT,
    exemplar_movie_ids  JSONB       NOT NULL DEFAULT '[]',
    parent_cluster_id   UUID        REFERENCES clusters(id) ON DELETE SET NULL,
    color_slot          INT         NOT NULL    -- stable hue index; inherited by carry-forward clusters
);
```

### `cluster_memberships`

Soft assignment of a movie to a cluster.

```sql
CREATE TABLE cluster_memberships (
    cluster_id  UUID    NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    movie_id    INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    probability FLOAT   NOT NULL,
    PRIMARY KEY (cluster_id, movie_id)
);

CREATE INDEX ON cluster_memberships (cluster_id);
CREATE INDEX ON cluster_memberships (movie_id);
```

### `conversation_snapshot_refs`

Join table linking conversations to every snapshot they have ever visited. Allows shared snapshots to survive individual conversation deletion.

```sql
CREATE TABLE conversation_snapshot_refs (
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    snapshot_id     UUID NOT NULL REFERENCES cluster_snapshots(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (conversation_id, snapshot_id)
);

CREATE INDEX ON conversation_snapshot_refs (snapshot_id);
```

### `concepts` and `concept_scores`

Oracle-derived linear axes and prototype concepts. Used by the `partition_by` and `drill_down` operations to split clusters along a meaningful dimension.

```sql
CREATE TABLE concepts (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT        NOT NULL,
    type       TEXT        NOT NULL CHECK (type IN ('linear_axis', 'prototype')),
    definition JSONB       NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE concept_scores (
    concept_id UUID    NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    movie_id   INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    score      FLOAT   NOT NULL,
    PRIMARY KEY (concept_id, movie_id)
);

CREATE INDEX ON concept_scores (concept_id);
```

---

## Entity-relationship summary

```
auth:
  roles ◄── users

catalogue:
  movies ──► movie_genres   ──► genres
     │
     ├──► cast_members      ──► people
     ├──► crew_members      ──► people
     └──► movie_keywords    ──► keywords

runtime:
  users ──► conversations ──► messages ──► concepts ◄── concept_scores ──► movies
                │
                ├──► conversation_snapshot_refs ──► cluster_snapshots (self-ref: parent_id)
                │                                         │
                │                                    clusters (self-ref: parent_cluster_id)
                │                                         │
                │                                    cluster_memberships ──► movies
                └──(current_cluster_snapshot_id, no FK)──► cluster_snapshots

eval harness:
  runs ──► eval_sessions ──► conversations
  personas ──► eval_sessions
  ground_truths ──► eval_sessions
  eval_sessions.condition: conversational | baseline | human
  eval_sessions.oracle_rating: 1–5 (NULL for human oracle)

  conversations ──► conversation_metrics  (1:1, written by eval harness)
               ├──► judge_scores           (1:N, written by eval harness)
               └──► turn_intents           (1:N, written by coordinator/baseline per turn)
```

---

## pgvector notes

- **Dimension**: 1024 for all three modalities. If any model changes, the `VECTOR(1024)` columns
  must be recreated.
- **Modalities**:
  - `text_embedding` / `review_embedding` — `BAAI/bge-large-en-v1.5` via `core/text_encoder.py`
    (model name and dimension come from `representation:` in the active YAML config).
  - `trailer_embedding` — `open_clip` `ViT-H-14 / laion2b_s32b_b79k` via `core/image_encoder.py`
    (hardcoded; mean-pooled over sampled trailer frames).
  - `text_embedding` is always present and fully indexed; `review_embedding` and
    `trailer_embedding` are optional with **partial** IVFFlat indexes (`WHERE … IS NOT NULL`).
- **Index**: `IVFFlat` with `lists = 100`, tuned for ~45k vectors. Scale `lists` proportionally
  with catalogue size.
- **Similarity**: cosine distance (`vector_cosine_ops`). Query: `ORDER BY embedding <=> $query_vec LIMIT k`.
- **Clusters carry no stored centroid**; the responder agent computes probability-weighted
  centroids on the fly from all soft-membership rows when deriving suggestion signals.
