CREATE TABLE runs (
    run_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    config_hash     TEXT        NOT NULL,
    config_snapshot JSONB       NOT NULL,
    seed            INTEGER     NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
