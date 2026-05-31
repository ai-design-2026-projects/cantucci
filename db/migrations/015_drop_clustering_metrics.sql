-- Drop intrinsic clustering-quality metrics (silhouette, mean_membership_prob,
-- noise_fraction) from conversation_metrics.  These measure only the HDBSCAN
-- algorithm fit and say nothing about the conversational / LLM system under
-- evaluation.  final_num_clusters is kept: it reflects the conversational
-- outcome (how the system shaped the final state), not intrinsic fit quality.
ALTER TABLE conversation_metrics
    DROP COLUMN IF EXISTS silhouette,
    DROP COLUMN IF EXISTS mean_membership_prob,
    DROP COLUMN IF EXISTS noise_fraction;
