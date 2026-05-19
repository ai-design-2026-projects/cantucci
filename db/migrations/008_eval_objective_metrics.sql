-- Add objective recall metrics to session_metrics.
-- Written by the eval harness after each session completes; NULL when the
-- session was abandoned before producing a final recommendation.
ALTER TABLE session_metrics
    ADD COLUMN IF NOT EXISTS precision_at_k FLOAT,
    ADD COLUMN IF NOT EXISTS recall_at_k    FLOAT,
    ADD COLUMN IF NOT EXISTS ndcg_at_k      FLOAT;

-- Add eval provenance columns to sessions.
-- NULL for live/human sessions; set by the eval runner for automated sessions.
-- persona_id and ground_truth_id are kebab-case slugs matching the YAML filenames
-- under configs/personas/ and configs/ground_truths/ respectively.
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS persona_id      VARCHAR(64),
    ADD COLUMN IF NOT EXISTS ground_truth_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS sessions_persona_id_idx      ON sessions (persona_id)      WHERE persona_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS sessions_ground_truth_id_idx ON sessions (ground_truth_id) WHERE ground_truth_id IS NOT NULL;
