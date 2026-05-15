-- Experimental run registry.
-- A run groups N sessions under one experimental condition (A–D in the eval spec)
-- with a single YAML config snapshot so every session in the run is reproducible
-- from (seed, config_snapshot) alone.
CREATE TABLE runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    -- baseline | uncertainty | random | boundary | popularity | component_test | human
    condition       VARCHAR(20) NOT NULL,
    -- 8-char SHA-256 prefix of the raw YAML config file bytes, from
    -- backend.settings.get_config_hash(). Replayability contract: this
    -- value matches the config_hash logged on every LLM call for sessions
    -- belonging to this run.
    config_hash     VARCHAR(8)  NOT NULL,
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
