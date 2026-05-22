import logging
import uuid
from typing import Any

from fastapi import APIRouter

from backend.data_access.cluster_snapshots.queries import (
    get_cluster_snapshot_with_clusters,
    get_conversation_cluster_snapshots,
    get_memberships,
)
from backend.exceptions import ClusterSnapshotNotFound
from backend.routers.dto.cluster_snapshots.dtos import ClusterDto, ClusterSnapshotDto, ClusterSnapshotGraphDto

log = logging.getLogger(__name__)

router = APIRouter(tags=["cluster-snapshots"])


@router.get("/cluster-snapshots/{cluster_snapshot_id}", response_model=ClusterSnapshotDto)
def get_cluster_snapshot_endpoint(cluster_snapshot_id: uuid.UUID) -> ClusterSnapshotDto:
    """Return a cluster snapshot with its full cluster list.

    Cluster ``size`` is computed as the count of membership rows for each cluster.

    Args:
        cluster_snapshot_id: Cluster snapshot UUID.

    Returns:
        ``ClusterSnapshotDto`` with clusters.

    Raises:
        HTTPException(404): If the cluster snapshot does not exist.
    """
    result = get_cluster_snapshot_with_clusters(cluster_snapshot_id)
    if result is None:
        raise ClusterSnapshotNotFound(cluster_snapshot_id)

    cluster_dtos = []
    for c in result.clusters:
        memberships = get_memberships(c.id)
        cluster_dtos.append(ClusterDto(
            id=c.id,
            label=c.label,
            summary=c.summary,
            exemplar_movie_ids=c.exemplar_movie_ids,
            parent_cluster_id=c.parent_cluster_id,
            size=len(memberships),
        ))

    s = result.cluster_snapshot
    return ClusterSnapshotDto(
        id=s.id,
        parent_id=s.parent_id,
        operation=s.operation,
        params=s.params,
        config_hash=s.config_hash,
        clusters=cluster_dtos,
        created_at=s.created_at,
    )


@router.get("/conversations/{conversation_id}/cluster-snapshots", response_model=ClusterSnapshotGraphDto)
def get_cluster_snapshot_graph(conversation_id: uuid.UUID) -> ClusterSnapshotGraphDto:
    """Return all cluster snapshot nodes for a conversation as a DAG for visualization.

    Each node includes id, parent_id, operation, and created_at — enough for
    an Obsidian-style force graph without loading full cluster membership data.

    Args:
        conversation_id: Conversation UUID.

    Returns:
        ``ClusterSnapshotGraphDto`` with all cluster snapshot nodes.
    """
    snapshots = get_conversation_cluster_snapshots(conversation_id)
    nodes: list[dict[str, Any]] = [
        {
            "id": str(s.id),
            "parent_id": str(s.parent_id) if s.parent_id else None,
            "operation": s.operation,
            "created_at": s.created_at.isoformat(),
        }
        for s in snapshots
    ]
    log.debug("cluster_snapshot_graph", extra={"conversation_id": str(conversation_id), "n_nodes": len(nodes)})
    return ClusterSnapshotGraphDto(cluster_snapshots=nodes)
