# Data Model

PostgreSQL schema for the conversational clustering system.
We distinguish two logical groups:
- **catalogue tables** — ingested once from the dataset, read-only during session runtime.
- **session tables** — written at runtime to capture the evolving state of each conversation.

Extensions required: `pgvector` (for `VECTOR` columns) and `pgcrypto` (for `gen_random_uuid()`).

---

## Catalogue tables

Populated once at ingest time by `db/ingest.py`, which loads the HuggingFace-hosted embedded parquet (produced by `db/scrape.py` → `notebooks/embed_in_colab.ipynb`) into the schema below. Read-only during the conversational loop.

### `movies`

Primary entity. One row per film.

```sql
CREATE TABLE movies (
    id                BIGINT       PRIMARY KEY,         -- TMDB integer ID
    imdb_id           VARCHAR(12)  UNIQUE,              -- e.g. "tt0111161"
    title             TEXT         NOT NULL,
    original_title    TEXT,
    original_language VARCHAR(10),                      -- ISO 639-1
    overview          TEXT,                             -- synopsis
    tagline           TEXT,
    release_date      DATE,
    release_year      SMALLINT     GENERATED ALWAYS AS (EXTRACT(YEAR FROM release_date)::SMALLINT) STORED,
    runtime           FLOAT,                            -- minutes
    budget            BIGINT,                           -- USD; 0 = unknown
    revenue           BIGINT,                           -- USD; 0 = unknown
    popularity        FLOAT,                            -- TMDB score at capture time
    vote_average      FLOAT,
    vote_count        INTEGER,
    bayesian_rating   FLOAT,                            -- (v*R + m*C)/(v+m) computed at ingest
    status            VARCHAR(30),                      -- Released, In Production, etc.
    adult             BOOLEAN      DEFAULT FALSE,
    video             BOOLEAN      DEFAULT FALSE,
    poster_path       TEXT,                             -- relative; prepend TMDB base URL at serve time
    homepage          TEXT,
    collection_id     BIGINT       REFERENCES collections(id),
    embedding         VECTOR(1024) NOT NULL             -- BAAI/bge-large-en-v1.5 on composite text
);

CREATE INDEX ON movies USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON movies (release_year);
CREATE INDEX ON movies (original_language);
CREATE INDEX ON movies (vote_count);
```

`bayesian_rating` uses `(v * R + m * C) / (v + m)` where `v = vote_count`, `R = vote_average`, `m` = minimum vote threshold, `C` = global mean. Use this as the ranking signal; raw `vote_average` should not be used alone.

The `embedding` column stores the pre-computed vector representation of the movie based on a composite of its metadata fields. This allows for efficient similarity search during retrieval.

The composite text should include the most salient attributes for clustering. We concatenate the following fields:

```
{title} {original_title} {overview} {tagline} {genres} {top3_cast} {director}
```

---

### `collections`

Extracted from the `belongs_to_collection` field on each TMDB API response. Represents franchises (e.g. "The Lord of the Rings Collection").

```sql
CREATE TABLE collections (
    id            BIGINT  PRIMARY KEY,     -- TMDB collection ID
    name          TEXT    NOT NULL,
    poster_path   TEXT,
    backdrop_path TEXT
);
```

---

### `genres`
Each movie can belong to multiple genres and each genre can apply to multiple movies, so we use a join table:

```sql
CREATE TABLE genres (
    id    INTEGER     PRIMARY KEY,         -- TMDB genre ID
    name  VARCHAR(50) NOT NULL
);

CREATE TABLE movie_genres (
    movie_id  BIGINT  NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    genre_id  INTEGER NOT NULL REFERENCES genres(id),
    PRIMARY KEY (movie_id, genre_id)
);
```

---

### `people`, `cast_members`, `crew_members`

The role is determined in the join tables (`cast_members` and `crew_members`) which reference `people.id` and specify the department/job or character played.

```sql
CREATE TABLE people (
    id      BIGINT   PRIMARY KEY,          -- TMDB person ID
    name    TEXT     NOT NULL,
    gender  SMALLINT                       -- 0 = unspecified, 1 = female, 2 = male
);

CREATE TABLE cast_members (
    movie_id   BIGINT      NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    person_id  BIGINT      NOT NULL REFERENCES people(id),
    character  TEXT,
    cast_order SMALLINT,                   -- billing order; 0 = top-billed
    credit_id  VARCHAR(30),
    PRIMARY KEY (movie_id, person_id, credit_id)
);
CREATE INDEX ON cast_members (person_id);

CREATE TABLE crew_members (
    movie_id   BIGINT      NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    person_id  BIGINT      NOT NULL REFERENCES people(id),
    department VARCHAR(50),
    job        VARCHAR(100),
    credit_id  VARCHAR(30),
    PRIMARY KEY (movie_id, person_id, credit_id)
);
CREATE INDEX ON crew_members (person_id);
CREATE INDEX ON crew_members (job);        -- frequent filter: job = 'Director'
```

---

### `keywords`
We define a separate `keywords` table and a many-to-many `movie_keywords` join table to capture the TMDB keywords associated with each movie. These are user-generated tags that can provide additional signals for clustering (e.g. "time travel", "based on novel", "space opera").

```sql
CREATE TABLE keywords (
    id    INTEGER PRIMARY KEY,
    name  TEXT    NOT NULL
);

CREATE TABLE movie_keywords (
    movie_id   BIGINT  NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    PRIMARY KEY (movie_id, keyword_id)
);
```

---

### `production_companies`
Some movies are produced by multiple companies, and some companies produce multiple movies, so we use a join table:

```sql
CREATE TABLE production_companies (
    id    BIGINT PRIMARY KEY,
    name  TEXT   NOT NULL
);
```

Again, many-to-many relationships to capture the spoken languages and production countries for each movie:

```sql
CREATE TABLE movie_companies (
    movie_id   BIGINT NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL REFERENCES production_companies(id),
    PRIMARY KEY (movie_id, company_id)
);
```

---

### `languages` and `countries`

```sql
CREATE TABLE languages (
    iso_639_1 CHAR(2) PRIMARY KEY,
    name      TEXT    NOT NULL
);

CREATE TABLE movie_spoken_languages (
    movie_id  BIGINT  NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    iso_639_1 CHAR(2) NOT NULL REFERENCES languages(iso_639_1),
    PRIMARY KEY (movie_id, iso_639_1)
);

CREATE TABLE countries (
    iso_3166_1 CHAR(2) PRIMARY KEY,
    name       TEXT    NOT NULL
);

CREATE TABLE movie_countries (
    movie_id   BIGINT  NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    iso_3166_1 CHAR(2) NOT NULL REFERENCES countries(iso_3166_1),
    PRIMARY KEY (movie_id, iso_3166_1)
);
```

---

## Auth tables

### `roles` and `users`

```sql
CREATE TABLE roles (
    id   SERIAL      PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL    -- 'user' | 'admin'
);

CREATE TABLE users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT        UNIQUE NOT NULL,
    password_hash TEXT        NOT NULL,
    role_id       INTEGER     NOT NULL REFERENCES roles(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Admin accounts are provisioned via `python -m db.create_user --role admin`; the register endpoint always creates `role = user`.

---

## Run & evaluation tables

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
    condition       VARCHAR(20) DEFAULT 'conversational',  -- conversational | baseline | human
    model_version   TEXT,
    ended_at        TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL DEFAULT 'running',  -- running | completed | aborted
    notes           TEXT
);
```

### `personas`

Write-once oracle persona definitions. New behaviour requires a new slug/row.

```sql
CREATE TABLE personas (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                TEXT        UNIQUE NOT NULL,
    verbosity           TEXT        NOT NULL DEFAULT 'medium',   -- terse | medium | verbose
    decisiveness        FLOAT       NOT NULL DEFAULT 0.5,        -- [0, 1]
    drift_probability   FLOAT       NOT NULL DEFAULT 0.0,
    contradiction_rate  FLOAT       NOT NULL DEFAULT 0.0,
    definition          JSONB       NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `ground_truths`

Taste targets for simulated oracle sessions. `description` is shown to the oracle; `target_movie_ids` and `spec` are hidden and used for spec-satisfaction scoring.

```sql
CREATE TABLE ground_truths (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug             TEXT        UNIQUE NOT NULL,
    description      TEXT        NOT NULL,
    seed_movie_ids   JSONB       NOT NULL DEFAULT '[]',
    target_movie_ids JSONB       NOT NULL DEFAULT '[]',
    spec             JSONB       NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `eval_sessions`

Links a conversation to a run, persona, and ground truth. `persona_id` and `ground_truth_id` are NULL for human-oracle sessions.

```sql
CREATE TABLE eval_sessions (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID        NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    conversation_id  UUID        UNIQUE NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    persona_id       UUID        REFERENCES personas (id) ON DELETE SET NULL,
    ground_truth_id  UUID        REFERENCES ground_truths (id) ON DELETE SET NULL,
    seed             BIGINT      NOT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'active',  -- active | converged | abandoned
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON eval_sessions (run_id);
```

### `conversation_metrics`

Deterministic eval metrics, 1:1 per conversation. Safe to recompute (PK = `conversation_id`, upsert on recompute). Token counts are omitted — only `cost_usd` is persisted in the live schema.

```sql
CREATE TABLE conversation_metrics (
    conversation_id      UUID          PRIMARY KEY REFERENCES conversations (id) ON DELETE CASCADE,
    converged            BOOLEAN       NOT NULL DEFAULT FALSE,
    turns_to_convergence SMALLINT,                                    -- NULL if not converged
    num_turns            SMALLINT      NOT NULL DEFAULT 0,
    avg_cognitive_load   FLOAT,
    final_num_clusters   SMALLINT,
    silhouette           FLOAT,                                       -- NULL if < 2 clusters
    mean_membership_prob FLOAT,
    noise_fraction       FLOAT,
    spec_satisfaction_rate FLOAT,                                     -- NULL for human sessions
    total_cost_usd       NUMERIC(10,4) NOT NULL DEFAULT 0,
    computed_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
```

### `judge_scores`

LLM-judge dimension scores. Append-only; `judge_prompt_hash` lets multiple judge versions coexist.

```sql
CREATE TABLE judge_scores (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id   UUID        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    dimension         VARCHAR(40) NOT NULL,  -- clustering_coherence | question_quality | label_accuracy | intent_alignment
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

Written at runtime by the conversational loop (`backend/agents/coordinator/`) to capture the evolving state of each conversation.

### `conversations`

One row per user conversation. `current_cluster_snapshot_id` is the live pointer to the most recent cluster state.

```sql
CREATE TABLE conversations (
    id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     UUID        REFERENCES users(id) ON DELETE SET NULL,
    current_cluster_snapshot_id UUID        REFERENCES cluster_snapshots(id),
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
    cost_usd        FLOAT       NOT NULL DEFAULT 0.0
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
    exemplar_movie_ids  JSONB       DEFAULT '[]',
    parent_cluster_id   UUID        REFERENCES clusters(id)
);
```

### `cluster_memberships`

Soft assignment of a movie to a cluster.

```sql
CREATE TABLE cluster_memberships (
    cluster_id  UUID    NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    movie_id    INTEGER NOT NULL REFERENCES movies(id),
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
    definition JSONB       DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE concept_scores (
    concept_id UUID    NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    movie_id   INTEGER NOT NULL REFERENCES movies(id),
    score      FLOAT   NOT NULL,
    PRIMARY KEY (concept_id, movie_id)
);

CREATE INDEX ON concept_scores (concept_id);
```

---

## Entity-relationship summary

```
catalogue:
  collections ◄── movies ──► movie_genres       ──► genres
                      │
                      ├──► cast_members          ──► people
                      ├──► crew_members          ──► people
                      ├──► movie_keywords        ──► keywords
                      ├──► movie_companies       ──► production_companies
                      ├──► movie_spoken_languages ──► languages
                      └──► movie_countries       ──► countries

runtime:
  roles ◄── users ──► conversations ──► messages
                            │
                            ├──► conversation_snapshot_refs ──► cluster_snapshots ──► clusters ──► cluster_memberships ──► movies
                            └── (current_cluster_snapshot_id) ──►    cluster_snapshots

eval harness:
  runs ──► eval_sessions ──► conversations
  personas ──►  eval_sessions
  ground_truths ──► eval_sessions

  conversations ──► conversation_metrics  (1:1, written by eval harness)
               └──► judge_scores           (1:N, written by eval harness)
```

---

## pgvector notes

- **Dimension**: 1024 (matches `BAAI/bge-large-en-v1.5`). If the model changes via `representation.model` / `representation.embedding_dim` in config, the column must be recreated.
- **Index**: `IVFFlat` with `lists = 100`, tuned for ~45k vectors. Scale `lists` proportionally with catalogue size.
- **Similarity**: cosine distance (`vector_cosine_ops`). Query: `ORDER BY embedding <=> $query_vec LIMIT k`.
- **Cluster centroids** (`clusters.centroid`) are not ANN-indexed — used for display and drift detection only.
