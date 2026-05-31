-- Remove operation_recall from conversation_metrics.
-- The deterministic GT-vs-trajectory comparison is replaced by the judge's
-- operation_appropriateness dimension, which is robust to concept string variation.
ALTER TABLE conversation_metrics DROP COLUMN IF EXISTS operation_recall;
