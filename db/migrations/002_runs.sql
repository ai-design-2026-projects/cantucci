-- Experimental run registry.
-- A run groups N sessions under one experimental condition (A–D in the eval spec)
-- with a single YAML config snapshot so every session in the run is reproducible
-- from (seed, config_snapshot) alone.
CREATE TABLE runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    -- baseline | uncertainty | random | boundary | popularity | component_test | human
    condition       VARCHAR(20) NOT NULL,
    -- SHA-256 hex of the canonical JSON of config_snapshot
    config_hash     CHAR(64)    NOT NULL,
    config_snapshot JSONB       NOT NULL,
    seed            BIGINT      NOT NULL,
    model_version   TEXT        NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    -- running | completed | aborted
    status          VARCHAR(20) NOT NULL DEFAULT 'running',
    notes           TEXT
);

CREATE INDEX ON runs (condition);
CREATE INDEX ON runs (config_hash);
