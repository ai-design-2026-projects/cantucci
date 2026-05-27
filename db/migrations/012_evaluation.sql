-- Evaluation subsystem tables: personas, ground truths, eval session wrappers,
-- deterministic metrics, and LLM-judge scores. All eval tables build on the
-- real runtime schema (conversations, cluster_snapshots) rather than the stale
-- sessions/turns abstraction described in earlier documentation.
--
-- Also extends the existing `runs` table (004) with eval-run registry columns.

-- Extend runs with eval-run registry fields (safe on an empty or non-empty table).
ALTER TABLE runs ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS condition VARCHAR(20) DEFAULT 'conversational';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS model_version TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'running';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS notes TEXT;

CREATE INDEX IF NOT EXISTS runs_condition_idx ON runs (condition);
CREATE INDEX IF NOT EXISTS runs_status_idx ON runs (status);

-- Oracle personas: write-once simulation profiles. New behaviour = new slug/row.
CREATE TABLE IF NOT EXISTS personas (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                TEXT        UNIQUE NOT NULL,
    verbosity           TEXT        NOT NULL DEFAULT 'medium',   -- terse | medium | verbose
    decisiveness        FLOAT       NOT NULL DEFAULT 0.5,        -- [0, 1]
    drift_probability   FLOAT       NOT NULL DEFAULT 0.0,        -- per-turn tangent probability
    contradiction_rate  FLOAT       NOT NULL DEFAULT 0.0,        -- per-turn contradiction probability
    definition          JSONB       NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ground truths: taste targets for simulated oracle sessions.
-- description is shown to the oracle; target_movie_ids and spec are kept hidden.
CREATE TABLE IF NOT EXISTS ground_truths (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug             TEXT        UNIQUE NOT NULL,
    description      TEXT        NOT NULL,       -- neutral taste description shown to the oracle
    seed_movie_ids   JSONB       NOT NULL DEFAULT '[]',  -- seed films used to expand the set
    target_movie_ids JSONB       NOT NULL DEFAULT '[]',  -- hidden expanded film set
    spec             JSONB       NOT NULL DEFAULT '{}',  -- positive/negative criteria for spec-satisfaction
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Eval sessions: experimental wrappers that attach a conversation to a run,
-- persona, and ground truth. NULL persona_id / ground_truth_id = human oracle.
CREATE TABLE IF NOT EXISTS eval_sessions (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID        NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    conversation_id  UUID        UNIQUE NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    persona_id       UUID        REFERENCES personas (id) ON DELETE SET NULL,
    ground_truth_id  UUID        REFERENCES ground_truths (id) ON DELETE SET NULL,
    seed             BIGINT      NOT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'active',   -- active | converged | abandoned
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS eval_sessions_run_id_idx ON eval_sessions (run_id);

-- Conversation metrics: 1:1 deterministic eval metrics per conversation.
-- Safe to recompute; PK = conversation_id (upsert on recompute).
-- Token counts are omitted: only cost_usd is persisted in the live schema.
CREATE TABLE IF NOT EXISTS conversation_metrics (
    conversation_id      UUID          PRIMARY KEY REFERENCES conversations (id) ON DELETE CASCADE,
    silhouette           FLOAT,                                       -- NULL if < 2 clusters
    mean_membership_prob FLOAT,
    noise_fraction       FLOAT,
    final_num_clusters   SMALLINT,
    spec_satisfaction_rate FLOAT,                                     -- NULL when no ground truth
    converged            BOOLEAN       NOT NULL DEFAULT FALSE,
    turns_to_convergence SMALLINT,                                    -- NULL if not converged
    num_turns            SMALLINT      NOT NULL DEFAULT 0,
    total_cost_usd       NUMERIC(10,4) NOT NULL DEFAULT 0,
    computed_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Judge scores: 1:N LLM-judge dimension scores per conversation.
-- Append-only; judge_prompt_hash allows multiple judge versions to coexist.
CREATE TABLE IF NOT EXISTS judge_scores (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id   UUID        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    dimension         VARCHAR(40) NOT NULL,   -- clustering_coherence | question_quality | label_accuracy | intent_alignment
    score             SMALLINT    NOT NULL CHECK (score BETWEEN 1 AND 5),
    rationale         TEXT,
    judge_model       TEXT        NOT NULL,
    judge_prompt_hash CHAR(64)    NOT NULL,   -- SHA-256 hex of the rendered judge prompt
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conversation_id, dimension, judge_prompt_hash)
);

CREATE INDEX IF NOT EXISTS judge_scores_conversation_id_idx ON judge_scores (conversation_id);
CREATE INDEX IF NOT EXISTS judge_scores_dimension_idx ON judge_scores (dimension);
