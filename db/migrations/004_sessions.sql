-- Session tables: written at runtime by the conversational loop.
-- See docs/specifications/architecture/data_schema.md §Session tables.
-- Extended beyond the spec: run_id, seed, config_hash, model_version, persona_id,
-- cost_limit_usd added to sessions for reproducibility (see CLAUDE.md §Data and state).

CREATE TABLE sessions (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id             UUID         NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    -- Per-session seed; combined with run seed for exact replay
    seed               BIGINT       NOT NULL,
    -- SHA-256 hex of the YAML config snapshot used for this session
    config_hash        CHAR(64)     NOT NULL,
    model_version      TEXT         NOT NULL,
    -- NULL for human oracles; set to persona identifier for LLM-simulated oracles
    persona_id         TEXT,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- active | converged | abandoned
    status             VARCHAR(20)  NOT NULL DEFAULT 'active',
    max_turns          INTEGER      NOT NULL DEFAULT 15,
    cost_limit_usd     NUMERIC(10,4),
    -- Populated at convergence: structured preference profile extracted from oracle feedback
    preference_profile JSONB
);

CREATE INDEX ON sessions (run_id);

CREATE TABLE turns (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_number       SMALLINT    NOT NULL,
    user_message      TEXT        NOT NULL,
    assistant_message TEXT,
    -- show | ask | stop
    step_type         VARCHAR(20),
    converged         BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, turn_number)
);

CREATE INDEX ON turns (session_id);

CREATE TABLE clusters (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id           UUID        NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    -- NULL for coarse clusters (level = 0)
    parent_cluster_id UUID        REFERENCES clusters(id),
    name              TEXT        NOT NULL,
    description       TEXT,
    -- 0 = coarse, 1 = fine (drilled into on oracle request)
    level             SMALLINT    NOT NULL DEFAULT 0,
    -- Mean embedding of assigned titles; used for drift detection and display only (not indexed for ANN)
    centroid          VECTOR(1024),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON clusters (session_id, turn_id);

CREATE TABLE cluster_assignments (
    id         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID    NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    movie_id   BIGINT  NOT NULL REFERENCES movies(id),
    -- Soft-assignment probability [0, 1]; scores across clusters for a given (movie, turn) sum to 1
    score      FLOAT   NOT NULL,
    -- Oracle explicitly rejected this title from this cluster
    excluded   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ON cluster_assignments (cluster_id);
CREATE INDEX ON cluster_assignments (movie_id);

CREATE TABLE oracle_feedback (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id        UUID        NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    -- global | cluster | point | instructional
    feedback_level VARCHAR(20) NOT NULL,
    -- accept | reject | split | merge | resolve_drift | constraint
    feedback_type  VARCHAR(30) NOT NULL,
    -- Cluster UUID or TMDB movie ID (as text) depending on feedback_level
    target_id      TEXT,
    content        TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON oracle_feedback (session_id);
CREATE INDEX ON oracle_feedback (feedback_type);
