-- Add a stable color slot to each cluster so the frontend can assign
-- maximally-distinguishable, operation-stable hues via the golden angle.
--
-- The slot is an integer inherited by carry-forward clusters and freshly
-- assigned (at max(existing)+1) for genuinely new clusters.  It is NOT
-- part of the snapshot cache key, so the replayability contract is unaffected.

ALTER TABLE clusters ADD COLUMN IF NOT EXISTS color_slot INT;

UPDATE clusters
SET color_slot = sub.rn
FROM (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY cluster_snapshot_id ORDER BY id) - 1 AS rn
    FROM clusters
) sub
WHERE clusters.id = sub.id
  AND clusters.color_slot IS NULL;

ALTER TABLE clusters ALTER COLUMN color_slot SET NOT NULL;
