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

These tables are written by the evaluation harness (not the live conversational loop) to group sessions into experimental conditions and store per-session and per-run results.

### `runs`

Groups N sessions under one experimental condition with a single config snapshot for replay.

```sql
CREATE TABLE runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    condition       VARCHAR(20) NOT NULL,   -- baseline | uncertainty | random | boundary | popularity | component_test | human
    config_hash     VARCHAR(8)  NOT NULL,   -- 8-char SHA-256 prefix of raw YAML config bytes
    config_snapshot JSONB       NOT NULL,
    seed            BIGINT      NOT NULL,
    model_version   TEXT        NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL DEFAULT 'running',  -- running | completed | aborted
    notes           TEXT
);

CREATE INDEX ON runs (condition);
CREATE INDEX ON runs (config_hash);
```

### `session_metrics`

One row per session; computed after the session ends by the eval harness. Safe to rewrite on recompute (PK = `session_id`).

```sql
CREATE TABLE session_metrics (
    session_id           UUID          PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    converged            BOOLEAN       NOT NULL,
    turns_to_convergence SMALLINT,              -- NULL if abandoned
    avg_cognitive_load   FLOAT,
    explicit_acceptance  BOOLEAN       NOT NULL DEFAULT FALSE,
    drift_events         SMALLINT      NOT NULL DEFAULT 0,
    total_input_tokens   INTEGER       NOT NULL DEFAULT 0,
    total_output_tokens  INTEGER       NOT NULL DEFAULT 0,
    total_cost_usd       NUMERIC(10,4) NOT NULL DEFAULT 0,
    precision_at_k       FLOAT,                -- fraction of top-K hits in gt_movie_ids
    recall_at_k          FLOAT,                -- fraction of gt_movie_ids recovered in top-K
    ndcg_at_k            FLOAT,                -- normalised discounted cumulative gain at K
    computed_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
```

### `judge_scores`

LLM-judge dimension scores. Append-only; `judge_prompt_hash` lets multiple judge versions coexist.

```sql
CREATE TABLE judge_scores (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    dimension         VARCHAR(40) NOT NULL,    -- clustering_coherence | question_quality | profile_fidelity
    score             SMALLINT    NOT NULL CHECK (score BETWEEN 1 AND 5),
    rationale         TEXT,
    judge_model       TEXT        NOT NULL,
    judge_prompt_hash CHAR(64)    NOT NULL,    -- SHA-256 hex of rendered judge prompt
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, dimension, judge_prompt_hash)
);

CREATE INDEX ON judge_scores (session_id);
CREATE INDEX ON judge_scores (dimension);
```

---

## Session tables

To store various per session data, we have the following tables. These are written to at runtime by the conversational loop to capture the evolving state of each session, including the turns taken, the cluster states, and the oracle feedback.

A `uuid` is generated for each session and turn to serve as stable identifiers that can be referenced across tables. The `session_id` foreign key links all related records together, while `turn_number` captures the sequential order of turns within a session.

### `sessions`

Table that identifies a single session. Each time a new conversation is started, a new session is created. The `status` field tracks whether the session is active, has converged, or was abandoned. The `config_hash` allows us to link back to the exact configuration used for this session for reproducibility. The `preference_profile` is populated at convergence with the structured profile extracted from oracle feedback.

```sql
CREATE TABLE sessions (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id             UUID         NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seed               BIGINT       NOT NULL,          -- per-session RNG seed for exact replay
    config_hash        VARCHAR(8)   NOT NULL,           -- 8-char SHA-256 prefix; must match parent run
    model_version      TEXT         NOT NULL,
    user_id            UUID         REFERENCES users(id) ON DELETE SET NULL,  -- NULL for anonymous
    persona_id         VARCHAR(64),                    -- NULL for human oracles; slug for simulated
    ground_truth_id    VARCHAR(64),                    -- NULL for human sessions; slug for eval runs
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status             VARCHAR(20)  NOT NULL DEFAULT 'active',  -- active | converged | abandoned
    max_turns          INTEGER      NOT NULL DEFAULT 15,
    cost_limit_usd     NUMERIC(10,4),
    preference_profile JSONB                           -- populated at convergence by the profile agent
);

CREATE INDEX ON sessions (run_id);
CREATE INDEX ON sessions (user_id);
CREATE INDEX ON sessions (persona_id) WHERE persona_id IS NOT NULL;
CREATE INDEX ON sessions (ground_truth_id) WHERE ground_truth_id IS NOT NULL;
```

---

### `turns`

One row per conversation turn.

```sql
CREATE TABLE turns (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_number       SMALLINT    NOT NULL,
    user_message      TEXT        NOT NULL,    -- raw oracle utterance
    assistant_message TEXT,                    -- system response (question or recommendation)
    step_type         VARCHAR(20),             -- show | ask | stop
    converged         BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, turn_number)
);

CREATE INDEX ON turns (session_id);
```

---

### `clusters`

Snapshot of cluster state after each turn. Supports a two-level hierarchy: `level = 0` coarse, `level = 1` fine.

```sql
CREATE TABLE clusters (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id           UUID        NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    parent_cluster_id UUID        REFERENCES clusters(id),  -- NULL for level=0
    name              TEXT        NOT NULL,
    description       TEXT,
    level             SMALLINT    NOT NULL DEFAULT 0,        -- 0 = coarse, 1 = fine
    centroid          VECTOR(1024),                          -- mean embedding; not indexed for ANN
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON clusters (session_id, turn_id);
```

`parent_cluster_id` encodes the two-level hierarchy: coarse clusters (`level = 0`) have `parent_cluster_id = NULL`; fine clusters (`level = 1`) reference their parent coarse cluster.

---

### `cluster_assignments`

Soft assignment of a film to a cluster for a given turn snapshot.

```sql
CREATE TABLE cluster_assignments (
    id         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID    NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    movie_id   BIGINT  NOT NULL REFERENCES movies(id),
    score      FLOAT   NOT NULL,           -- soft-assignment probability [0, 1]
    excluded   BOOLEAN NOT NULL DEFAULT FALSE  -- oracle explicitly rejected this film
);

CREATE INDEX ON cluster_assignments (cluster_id);
CREATE INDEX ON cluster_assignments (movie_id);
```

---

### `oracle_feedback`

Immutable log of every oracle action. Never updated; new rows only.

```sql
CREATE TABLE oracle_feedback (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id        UUID        NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    feedback_level VARCHAR(20) NOT NULL,  -- global | cluster | point | instructional
    feedback_type  VARCHAR(30) NOT NULL,  -- accept | reject | split | merge | resolve_drift | constraint
    target_id      TEXT,                  -- cluster UUID or TMDB movie ID as text, depending on level
    content        TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON oracle_feedback (session_id);
CREATE INDEX ON oracle_feedback (feedback_type);
```

---

## Entity-relationship summary

```
collections ◄── movies ──► movie_genres       ──► genres
                    │
                    ├──► cast_members          ──► people
                    ├──► crew_members          ──► people
                    ├──► movie_keywords        ──► keywords
                    ├──► movie_companies       ──► production_companies
                    ├──► movie_spoken_languages ──► languages
                    └──► movie_countries       ──► countries

roles ◄── users ──► sessions
              │
runs ─────────┤
              └──► turns ──► clusters ──► cluster_assignments ──► movies
                        └──► oracle_feedback

sessions ──► session_metrics  (1:1, written by eval harness)
         └──► judge_scores     (1:N, written by eval harness)
```

---

## pgvector notes

- **Dimension**: 1024 (matches `BAAI/bge-large-en-v1.5`). If the model changes via `representation.model` / `representation.embedding_dim` in config, the column must be recreated.
- **Index**: `IVFFlat` with `lists = 100`, tuned for ~45k vectors. Scale `lists` proportionally with catalogue size.
- **Similarity**: cosine distance (`vector_cosine_ops`). Query: `ORDER BY embedding <=> $query_vec LIMIT k`.
- **Cluster centroids** (`clusters.centroid`) are not ANN-indexed — used for display and drift detection only.
