-- Evaluation subsystem tables: personas, ground truths, eval session wrappers,
-- per-turn intent trace, deterministic metrics, and LLM-judge scores.
-- All eval tables build on the real runtime schema (conversations, cluster_snapshots).
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
-- Dials: verbosity (reply length) and patience (willingness to continue after misbehaviour).
CREATE TABLE IF NOT EXISTS personas (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT        UNIQUE NOT NULL,
    verbosity   TEXT        NOT NULL DEFAULT 'medium',  -- terse | medium | verbose
    patience    FLOAT       NOT NULL DEFAULT 0.5,       -- [0, 1]
    definition  JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ground truths: ordered navigation trajectories for simulated oracle sessions.
-- intent_description is shown to the oracle; operations is its private to-do list.
CREATE TABLE IF NOT EXISTS ground_truths (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug               TEXT        UNIQUE NOT NULL,
    version            SMALLINT    NOT NULL DEFAULT 1,
    intent_description TEXT        NOT NULL,
    operations         JSONB       NOT NULL,  -- ordered list[{op: str, concept: str}]
    seed_movie_ids     JSONB,                 -- nullable; movie ids used by builder for audit
    prompt_hash        CHAR(64)    NOT NULL,  -- SHA-256 of the GT builder prompts at creation
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Eval sessions: experimental wrappers that attach a conversation to a run,
-- persona, and ground truth. NULL persona_id / ground_truth_id = human oracle.
CREATE TABLE IF NOT EXISTS eval_sessions (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                UUID        NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    conversation_id       UUID        UNIQUE NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    persona_id            UUID        REFERENCES personas (id) ON DELETE SET NULL,
    ground_truth_id       UUID        REFERENCES ground_truths (id) ON DELETE SET NULL,
    seed                  BIGINT      NOT NULL,
    condition             VARCHAR(20) NOT NULL DEFAULT 'conversational',  -- mirrors runs.condition
    status                VARCHAR(20) NOT NULL DEFAULT 'active',          -- active | finished_trajectory | finished_misbehaviour | finished_budget
    termination_rationale TEXT,                                           -- free-text rationale from oracle on stop
    oracle_rating         SMALLINT    CHECK (oracle_rating IS NULL OR oracle_rating BETWEEN 1 AND 5),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS eval_sessions_run_id_idx ON eval_sessions (run_id);

-- Per-turn intent trace: persists the structured intent info the coordinator
-- computes each turn. Required for operation_recall and clarifier_trigger_rate.
-- One row per (conversation, turn, mode); compound turns produce multiple rows.
CREATE TABLE IF NOT EXISTS turn_intents (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id   UUID        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    turn_number       SMALLINT    NOT NULL,  -- 1-based ordinal
    mode              VARCHAR(40) NOT NULL,  -- any NavigationMode or DialogueMode value
    concept           TEXT,
    target_cluster_id UUID,                 -- not FK'd; snapshots may rotate
    confidence        FLOAT       NOT NULL,
    clarifier_fired   BOOLEAN     NOT NULL DEFAULT FALSE,
    raw_intent        JSONB       NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conversation_id, turn_number, mode)
);

CREATE INDEX IF NOT EXISTS turn_intents_conversation_turn_idx ON turn_intents (conversation_id, turn_number);

-- Conversation metrics: 1:1 deterministic eval metrics per conversation.
-- Safe to recompute; PK = conversation_id (upsert on recompute).
CREATE TABLE IF NOT EXISTS conversation_metrics (
    conversation_id       UUID          PRIMARY KEY REFERENCES conversations (id) ON DELETE CASCADE,
    silhouette            FLOAT,                                      -- NULL if < 2 clusters
    mean_membership_prob  FLOAT,
    noise_fraction        FLOAT,
    final_num_clusters    SMALLINT,
    operation_recall      FLOAT,                                      -- NULL when no ground truth
    clarifier_trigger_rate FLOAT,
    num_turns             SMALLINT      NOT NULL DEFAULT 0,
    num_operations        SMALLINT      NOT NULL DEFAULT 0,
    total_cost_usd        NUMERIC(10,4) NOT NULL DEFAULT 0,
    computed_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Judge scores: 1:N LLM-judge dimension scores per conversation.
-- Append-only; judge_prompt_hash allows multiple judge versions to coexist.
-- Dimensions: operation_appropriateness | label_accuracy | suggestion_meaningfulness |
--             explanation_quality | intent_alignment
CREATE TABLE IF NOT EXISTS judge_scores (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id   UUID        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    dimension         VARCHAR(40) NOT NULL,
    score             SMALLINT    NOT NULL CHECK (score BETWEEN 1 AND 5),
    rationale         TEXT,
    judge_model       TEXT        NOT NULL,
    judge_prompt_hash CHAR(64)    NOT NULL,  -- SHA-256 hex of the rendered judge prompt
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conversation_id, dimension, judge_prompt_hash)
);

CREATE INDEX IF NOT EXISTS judge_scores_conversation_id_idx ON judge_scores (conversation_id);
CREATE INDEX IF NOT EXISTS judge_scores_dimension_idx ON judge_scores (dimension);
