import json
import logging
import uuid
from typing import Any

from backend.data_access.connection import transaction
from backend.data_access.cluster_snapshots.types import (
    ClusterMembershipRow,
    ClusterRow,
    ClusterSnapshotRow,
    ClusterSnapshotWithClusters,
)

log = logging.getLogger(__name__)


def create_cluster_snapshot(
    operation: str,
    params: dict[str, Any],
    conversation_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a new cluster snapshot row and return its UUID.

    Args:
        operation:       Name of the operation that produced this snapshot.
        params:          Replayability parameters as a dict.
        conversation_id: Parent conversation UUID, or None for the root snapshot.
        parent_id:       Parent cluster snapshot UUID, or None for the root.

    Returns:
        UUID of the newly created cluster snapshot.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO cluster_snapshots (conversation_id, parent_id, operation, params)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (conversation_id, parent_id, operation, json.dumps(params)),
        ).fetchone()
    cluster_snapshot_id: uuid.UUID = row[0]
    log.debug("cluster_snapshot_created", extra={"cluster_snapshot_id": str(cluster_snapshot_id), "operation": operation})
    return cluster_snapshot_id


def create_cluster(
    cluster_snapshot_id: uuid.UUID,
    label: str,
    summary: str | None,
    exemplar_movie_ids: list[int],
    parent_cluster_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a cluster row and return its UUID.

    Args:
        cluster_snapshot_id: Parent cluster snapshot UUID.
        label:               Human-readable label.
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
    return row[0]


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


def get_cluster_snapshot(cluster_snapshot_id: uuid.UUID) -> ClusterSnapshotRow | None:
    """Fetch a single cluster snapshot row by ID.

    Args:
        cluster_snapshot_id: UUID to look up.

    Returns:
        ``ClusterSnapshotRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, conversation_id, parent_id, operation, params, created_at FROM cluster_snapshots WHERE id = %s",
            (cluster_snapshot_id,),
        ).fetchone()
    if row is None:
        return None
    return ClusterSnapshotRow(
        id=row[0],
        conversation_id=row[1],
        parent_id=row[2],
        operation=row[3],
        params=row[4],
        created_at=row[5],
    )


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

    clusters = [
        ClusterRow(
            id=r[0],
            cluster_snapshot_id=r[1],
            label=r[2],
            summary=r[3],
            exemplar_movie_ids=list(r[4]) if r[4] else [],
            parent_cluster_id=r[5],
        )
        for r in rows
    ]
    log.debug("get_cluster_snapshot_with_clusters", extra={"cluster_snapshot_id": str(cluster_snapshot_id), "n_clusters": len(clusters)})
    return ClusterSnapshotWithClusters(cluster_snapshot=snapshot, clusters=clusters)


def get_conversation_cluster_snapshots(conversation_id: uuid.UUID) -> list[ClusterSnapshotRow]:
    """Return all cluster snapshots for a conversation ordered by creation time.

    Args:
        conversation_id: Parent conversation UUID.

    Returns:
        List of ``ClusterSnapshotRow`` ordered by created_at ascending.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, conversation_id, parent_id, operation, params, created_at
            FROM cluster_snapshots
            WHERE conversation_id = %s
            ORDER BY created_at
            """,
            (conversation_id,),
        ).fetchall()
    return [
        ClusterSnapshotRow(id=r[0], conversation_id=r[1], parent_id=r[2], operation=r[3], params=r[4], created_at=r[5])
        for r in rows
    ]


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
    return [ClusterMembershipRow(cluster_id=r[0], movie_id=r[1], probability=r[2]) for r in rows]
