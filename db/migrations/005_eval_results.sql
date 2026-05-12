-- Evaluation result tables.
-- session_metrics: one row per session; deterministic per-session metrics.
-- judge_scores: one row per (session, dimension, judge_prompt_hash); LLM-judge output.
-- Both are retrievable per run via JOIN to sessions.run_id.

CREATE TABLE session_metrics (
    session_id             UUID          PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    -- NULL if session was abandoned before convergence
    turns_to_convergence   SMALLINT,
    avg_cognitive_load     FLOAT,
    converged              BOOLEAN       NOT NULL,
    explicit_acceptance    BOOLEAN       NOT NULL DEFAULT FALSE,
    drift_events           SMALLINT      NOT NULL DEFAULT 0,
    total_input_tokens     INTEGER       NOT NULL DEFAULT 0,
    total_output_tokens    INTEGER       NOT NULL DEFAULT 0,
    total_cost_usd         NUMERIC(10,4) NOT NULL DEFAULT 0,
    computed_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE judge_scores (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    -- clustering_coherence | question_quality | profile_fidelity
    dimension         VARCHAR(40) NOT NULL,
    score             SMALLINT    NOT NULL CHECK (score BETWEEN 1 AND 5),
    rationale         TEXT,
    judge_model       TEXT        NOT NULL,
    -- SHA-256 hex of the judge prompt file; lets multiple judge versions coexist
    judge_prompt_hash CHAR(64)    NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, dimension, judge_prompt_hash)
);

CREATE INDEX ON judge_scores (session_id);
CREATE INDEX ON judge_scores (dimension);
