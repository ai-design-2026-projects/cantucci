-- Snapshot cache: make every cluster_snapshot deterministically reusable.
--   1. Add config_hash to identify which clustering config produced the snapshot.
--   2. Move conversation ownership into a join table so a snapshot can be
--      referenced by multiple conversations.
--   3. Drop the direct conversation_id column (was ON DELETE CASCADE, which
--      would have nuked shared snapshots when any one referencing conversation
--      was deleted).
--   4. Add a unique cache-key index over (parent_id, operation, params, config_hash).

ALTER TABLE cluster_snapshots ADD COLUMN config_hash TEXT;

UPDATE cluster_snapshots
SET config_hash = COALESCE(
    (SELECT config_hash FROM runs ORDER BY created_at DESC LIMIT 1),
    'unknown'
);

ALTER TABLE cluster_snapshots ALTER COLUMN config_hash SET NOT NULL;

CREATE TABLE conversation_snapshot_refs (
    conversation_id UUID        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    snapshot_id     UUID        NOT NULL REFERENCES cluster_snapshots (id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (conversation_id, snapshot_id)
);

CREATE INDEX conversation_snapshot_refs_snapshot_idx
    ON conversation_snapshot_refs (snapshot_id);

INSERT INTO conversation_snapshot_refs (conversation_id, snapshot_id, created_at)
SELECT conversation_id, id, created_at
FROM cluster_snapshots
WHERE conversation_id IS NOT NULL;

ALTER TABLE cluster_snapshots DROP COLUMN conversation_id;

-- NULLS NOT DISTINCT so the root snapshot (parent_id IS NULL) is also covered
-- by the cache key; without it, NULL parent_ids would all be treated as distinct
-- and we could end up with multiple "identical" root snapshots.
CREATE UNIQUE INDEX cluster_snapshots_cache_key_idx
    ON cluster_snapshots (parent_id, operation, params, config_hash) NULLS NOT DISTINCT;
