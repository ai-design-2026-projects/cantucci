import json
import logging
import uuid
from collections import defaultdict
from typing import Any

from backend.data_access.connection import transaction
from backend.data_access.cluster_snapshots.types import (
    ClusterMembershipRow,
    ClusterRow,
    ClusterSnapshotRow,
    ClusterSnapshotWithClusters,
)
from backend.settings import get_config_hash

log = logging.getLogger(__name__)

_FLOAT_PRECISION = 8


def canonicalize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic, JSON-stable copy of *params* for cache keying.

    Recursively sorts dict keys, rounds floats to a fixed precision, and
    coerces numpy scalars / tuples / sets into native JSON-friendly types so
    that two equal-meaning param dicts hash to the same JSONB bytes in the
    unique cache-key index.

    Args:
        params: Operation parameters dict.

    Returns:
        A new dict with stable ordering and normalized scalar types.
    """
    def _walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: _walk(value[k]) for k in sorted(value.keys())}
        if isinstance(value, (list, tuple)):
            return [_walk(v) for v in value]
        if isinstance(value, set):
            return sorted(_walk(v) for v in value)
        if isinstance(value, float):
            return round(float(value), _FLOAT_PRECISION)
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return int(value)
        return value

    return _walk(params)


def create_cluster_snapshot(
    operation: str,
    params: dict[str, Any],
    config_hash: str,
    parent_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a new cluster snapshot row and return its UUID.

    The caller is responsible for canonicalizing *params* (via
    ``canonicalize_params``) before calling, so the unique cache-key index
    can detect duplicates.

    Args:
        operation:   Name of the operation that produced this snapshot.
        params:      Replayability parameters as a dict (already canonicalized).
        config_hash: Active YAML config hash (matches ``backend.settings.get_config_hash``).
        parent_id:   Parent cluster snapshot UUID, or None for the root.

    Returns:
        UUID of the newly created cluster snapshot.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO cluster_snapshots (parent_id, operation, params, config_hash)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (parent_id, operation, json.dumps(params), config_hash),
        ).fetchone()
    cluster_snapshot_id: uuid.UUID = row["id"]
    log.debug("cluster_snapshot_created", extra={"cluster_snapshot_id": str(cluster_snapshot_id), "operation": operation})
    return cluster_snapshot_id


def find_cached_snapshot(
    parent_id: uuid.UUID | None,
    operation: str,
    params: dict[str, Any],
    config_hash: str,
) -> uuid.UUID | None:
    """Look up an existing snapshot with the same ``(parent, operation, params, config_hash)``.

    Caller must pass *params* through ``canonicalize_params`` first; the
    underlying unique index is byte-equal on the JSONB column.

    Args:
        parent_id:   Parent snapshot UUID, or None for a root-level lookup.
        operation:   Operation name (e.g. ``"drill_down"``).
        params:      Canonicalized params dict.
        config_hash: Active YAML config hash.

    Returns:
        UUID of the cached snapshot if it exists, else None.
    """
    with transaction() as conn:
        if parent_id is None:
            row = conn.execute(
                """
                SELECT id FROM cluster_snapshots
                WHERE parent_id IS NULL
                  AND operation = %s
                  AND params = %s::jsonb
                  AND config_hash = %s
                LIMIT 1
                """,
                (operation, json.dumps(params), config_hash),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id FROM cluster_snapshots
                WHERE parent_id = %s
                  AND operation = %s
                  AND params = %s::jsonb
                  AND config_hash = %s
                LIMIT 1
                """,
                (parent_id, operation, json.dumps(params), config_hash),
            ).fetchone()
    return row["id"] if row else None


def record_conversation_snapshot_ref(conversation_id: uuid.UUID, snapshot_id: uuid.UUID) -> None:
    """Record that *conversation_id* has touched *snapshot_id*.

    Idempotent: re-recording the same pair is a no-op.

    Args:
        conversation_id: Conversation UUID.
        snapshot_id:     Cluster snapshot UUID.
    """
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO conversation_snapshot_refs (conversation_id, snapshot_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (conversation_id, snapshot_id),
        )


def create_cluster(
    cluster_snapshot_id: uuid.UUID,
    label: str | None,
    summary: str | None,
    exemplar_movie_ids: list[int],
    parent_cluster_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a cluster row and return its UUID.

    Args:
        cluster_snapshot_id: Parent cluster snapshot UUID.
        label:               Human-readable label, or None for unlabeled root clusters.
        summary:             One-sentence summary, or None.
        exemplar_movie_ids:  Top movie IDs by probability.
        parent_cluster_id:   UUID of the source cluster for drill-down operations.

    Returns:
        UUID of the newly created cluster.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO clusters (cluster_snapshot_id, label, summary, exemplar_movie_ids, parent_cluster_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (cluster_snapshot_id, label, summary, json.dumps(exemplar_movie_ids), parent_cluster_id),
        ).fetchone()
    return row["id"]


def create_memberships(memberships: list[tuple[uuid.UUID, int, float]]) -> None:
    """Bulk-insert cluster membership rows.

    Args:
        memberships: List of ``(cluster_id, movie_id, probability)`` tuples.
    """
    if not memberships:
        return
    with transaction() as conn:
        conn.executemany(
            "INSERT INTO cluster_memberships (cluster_id, movie_id, probability) VALUES (%s, %s, %s)",
            memberships,
        )
    log.debug("memberships_inserted", extra={"count": len(memberships)})


def update_cluster_label(cluster_id: uuid.UUID, label: str, summary: str | None) -> None:
    """Persist a generated label and summary for an existing cluster.

    Args:
        cluster_id: UUID of the cluster to update.
        label:      Generated label string.
        summary:    Generated summary, or None.
    """
    with transaction() as conn:
        conn.execute(
            "UPDATE clusters SET label = %s, summary = %s WHERE id = %s",
            (label, summary, cluster_id),
        )
    log.debug("cluster_label_updated", extra={"cluster_id": str(cluster_id), "label": label})


def get_root_cluster_snapshot() -> ClusterSnapshotRow | None:
    """Return the most recent root cluster snapshot (``parent_id IS NULL, operation = 'base'``).

    Returns:
        The most recently created root ``ClusterSnapshotRow``, or None if none exists.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT id, parent_id, operation, params, config_hash, created_at
            FROM cluster_snapshots
            WHERE parent_id IS NULL AND operation = 'base'
            ORDER BY created_at DESC
            LIMIT 1
            """,
        ).fetchone()
    return ClusterSnapshotRow.from_row(row) if row else None


def get_cluster_snapshot(cluster_snapshot_id: uuid.UUID) -> ClusterSnapshotRow | None:
    """Fetch a single cluster snapshot row by ID.

    Args:
        cluster_snapshot_id: UUID to look up.

    Returns:
        ``ClusterSnapshotRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, parent_id, operation, params, config_hash, created_at FROM cluster_snapshots WHERE id = %s",
            (cluster_snapshot_id,),
        ).fetchone()
    if row is None:
        return None
    return ClusterSnapshotRow.from_row(row)


def get_cluster_snapshot_with_clusters(cluster_snapshot_id: uuid.UUID) -> ClusterSnapshotWithClusters | None:
    """Fetch a cluster snapshot and all its clusters.

    Args:
        cluster_snapshot_id: UUID to look up.

    Returns:
        ``ClusterSnapshotWithClusters`` if found, ``None`` otherwise.
    """
    snapshot = get_cluster_snapshot(cluster_snapshot_id)
    if snapshot is None:
        return None

    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, cluster_snapshot_id, label, summary, exemplar_movie_ids, parent_cluster_id
            FROM clusters
            WHERE cluster_snapshot_id = %s
            """,
            (cluster_snapshot_id,),
        ).fetchall()

    clusters = [ClusterRow.from_row(r) for r in rows]
    log.debug("get_cluster_snapshot_with_clusters", extra={"cluster_snapshot_id": str(cluster_snapshot_id), "n_clusters": len(clusters)})
    return ClusterSnapshotWithClusters(cluster_snapshot=snapshot, clusters=clusters)


def get_conversation_cluster_snapshots(conversation_id: uuid.UUID) -> list[ClusterSnapshotRow]:
    """Return all snapshots that *conversation_id* has touched, ordered by ref creation time.

    Joins through ``conversation_snapshot_refs`` so that snapshots reused
    from the global cache (and therefore not directly "owned" by this
    conversation) are still included in the listing.

    Args:
        conversation_id: Conversation UUID.

    Returns:
        List of ``ClusterSnapshotRow`` ordered by ref ``created_at`` ascending.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT cs.id, cs.parent_id, cs.operation, cs.params, cs.config_hash, cs.created_at
            FROM cluster_snapshots cs
            JOIN conversation_snapshot_refs r ON r.snapshot_id = cs.id
            WHERE r.conversation_id = %s
            ORDER BY r.created_at
            """,
            (conversation_id,),
        ).fetchall()
    return [ClusterSnapshotRow.from_row(r) for r in rows]


def create_root_snapshot_from_assignments(
    movie_ids: list[int],
    cluster_ids: list[int],
    cluster_probs: list[float],
    params: dict[str, Any],
    n_exemplars: int = 15,
) -> uuid.UUID:
    """Build a root cluster snapshot from offline primary cluster assignments.

    Creates the snapshot, all clusters (without labels), and all primary-assignment
    memberships in a single transaction. Called at ingest time after the offline
    embedding pipeline has produced cluster_ids and cluster_probs columns in the
    parquet artifact. The active config hash is stamped on the snapshot so the
    snapshot cache can key on it.

    Args:
        movie_ids:    TMDB IDs in row order (must match array row order).
        cluster_ids:  Primary cluster index per movie (0-based, from argmax of
                      soft membership probabilities).
        cluster_probs: Soft-membership probability of the primary cluster.
        params:       Replayability parameters (UMAP + HDBSCAN settings).
        n_exemplars:  Maximum number of exemplar movie IDs to store per cluster.

    Returns:
        UUID of the newly created root cluster snapshot.
    """
    canon_params = canonicalize_params(params)
    config_hash = get_config_hash()
    buckets: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for movie_id, cid, prob in zip(movie_ids, cluster_ids, cluster_probs):
        buckets[cid].append((movie_id, prob))

    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO cluster_snapshots (parent_id, operation, params, config_hash)
            VALUES (NULL, 'base', %s, %s)
            RETURNING id
            """,
            (json.dumps(canon_params), config_hash),
        ).fetchone()
        snapshot_id: uuid.UUID = row["id"]

        cluster_uuid_map: dict[int, uuid.UUID] = {}
        for cid in sorted(buckets.keys()):
            movies_in_cluster = sorted(buckets[cid], key=lambda x: x[1], reverse=True)
            exemplar_ids = [m[0] for m in movies_in_cluster[:n_exemplars]]
            cluster_row = conn.execute(
                """
                INSERT INTO clusters (cluster_snapshot_id, label, summary, exemplar_movie_ids, parent_cluster_id)
                VALUES (%s, NULL, NULL, %s, NULL)
                RETURNING id
                """,
                (snapshot_id, json.dumps(exemplar_ids)),
            ).fetchone()
            cluster_uuid_map[cid] = cluster_row["id"]

        membership_rows = [
            (cluster_uuid_map[cid], movie_id, prob)
            for movie_id, cid, prob in zip(movie_ids, cluster_ids, cluster_probs)
        ]
        conn.executemany(
            "INSERT INTO cluster_memberships (cluster_id, movie_id, probability) VALUES (%s, %s, %s)",
            membership_rows,
        )

    log.info(
        "root_snapshot_created",
        extra={
            "snapshot_id": str(snapshot_id),
            "n_clusters": len(buckets),
            "n_memberships": len(membership_rows),
            "config_hash": config_hash,
        },
    )
    return snapshot_id


def count_snapshot_children(snapshot_id: uuid.UUID) -> int:
    """Return the number of cluster snapshots that reference *snapshot_id* as their parent.

    Args:
        snapshot_id: Cluster snapshot UUID to check.

    Returns:
        Count of child snapshots (0 if leaf).
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM cluster_snapshots WHERE parent_id = %s",
            (snapshot_id,),
        ).fetchone()
    return int(row["n"])


def delete_cluster_snapshot(snapshot_id: uuid.UUID) -> None:
    """Hard-delete a leaf cluster snapshot.

    Updates any conversation whose ``current_cluster_snapshot_id`` points to
    the deleted snapshot to point at the snapshot's parent instead (or NULL for
    root snapshots). Cascade FK constraints remove ``clusters``,
    ``cluster_memberships``, and ``conversation_snapshot_refs`` rows automatically
    (defined in migrations 006 and 009).

    Callers must verify the snapshot has no children before calling (e.g. via
    ``count_snapshot_children``), since child snapshots reference this ID as
    their ``parent_id``.

    Args:
        snapshot_id: Cluster snapshot UUID to delete.
    """
    with transaction() as conn:
        parent_row = conn.execute(
            "SELECT parent_id FROM cluster_snapshots WHERE id = %s",
            (snapshot_id,),
        ).fetchone()
        if parent_row is not None:
            conn.execute(
                "UPDATE conversations SET current_cluster_snapshot_id = %s WHERE current_cluster_snapshot_id = %s",
                (parent_row["parent_id"], snapshot_id),
            )
        conn.execute(
            "DELETE FROM cluster_snapshots WHERE id = %s",
            (snapshot_id,),
        )
    log.info("cluster_snapshot_deleted", extra={"snapshot_id": str(snapshot_id)})


def get_memberships(cluster_id: uuid.UUID) -> list[ClusterMembershipRow]:
    """Return all membership rows for a cluster.

    Args:
        cluster_id: Cluster UUID.

    Returns:
        List of ``ClusterMembershipRow`` ordered by descending probability.
    """
    with transaction() as conn:
        rows = conn.execute(
            "SELECT cluster_id, movie_id, probability FROM cluster_memberships WHERE cluster_id = %s ORDER BY probability DESC",
            (cluster_id,),
        ).fetchall()
    return [ClusterMembershipRow.from_row(r) for r in rows]
