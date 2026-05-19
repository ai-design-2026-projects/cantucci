-- Add objective recall metrics to session_metrics.
-- Written by the eval harness after each session completes; NULL when the
-- session was abandoned before producing a final recommendation.
ALTER TABLE session_metrics
    ADD COLUMN IF NOT EXISTS precision_at_k FLOAT,
    ADD COLUMN IF NOT EXISTS recall_at_k    FLOAT,
    ADD COLUMN IF NOT EXISTS ndcg_at_k      FLOAT;
