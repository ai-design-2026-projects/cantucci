import logging
import uuid

from fastapi import APIRouter, HTTPException

from backend.data_access.cluster_snapshots.queries import (
    count_snapshot_children,
    delete_cluster_snapshot,
    get_cluster_snapshot_with_clusters,
    get_conversation_cluster_snapshots,
    get_memberships,
    get_root_cluster_snapshot,
)
from backend.exceptions import ClusterSnapshotNotFound, NotFoundError, SnapshotHasChildren
from backend.routers.dto.cluster_snapshots.dtos import ClusterMembershipDto, ClusterSnapshotDto, ClusterSnapshotGraphDto, SnapshotMemberDto
from backend.routers.dto.cluster_snapshots.build_snapshot import build_snapshot_dto, build_snapshot_graph_dto
import demo.utils.replay as _demo

log = logging.getLogger(__name__)

router = APIRouter(tags=["cluster-snapshots"])


@router.get("/cluster-snapshots/root", response_model=ClusterSnapshotDto)
def get_root_cluster_snapshot_endpoint() -> ClusterSnapshotDto:
    """Return the most recent root cluster snapshot.

    Used to show the full corpus silhouette before any conversation is active.
    No authentication required — the base corpus is public.

    Returns:
        ``ClusterSnapshotDto`` for the root snapshot.

    Raises:
        ClusterSnapshotNotFound: If no root snapshot has been ingested yet.
    """
    root = get_root_cluster_snapshot()
    if root is None:
        raise NotFoundError("No root cluster snapshot has been ingested yet")
    return build_snapshot_dto(root.id)


@router.get("/cluster-snapshots/{cluster_snapshot_id}", response_model=ClusterSnapshotDto)
def get_cluster_snapshot_endpoint(cluster_snapshot_id: uuid.UUID) -> ClusterSnapshotDto:
    """Return a cluster snapshot with its full cluster list.

    Args:
        cluster_snapshot_id: Cluster snapshot UUID.

    Returns:
        ``ClusterSnapshotDto`` with clusters and argmax member list.

    Raises:
        ClusterSnapshotNotFound: If the cluster snapshot does not exist.
    """
    if _demo.is_replay_mode():
        recorded = _demo.get_recorded_snapshot(str(cluster_snapshot_id))
        if recorded is not None:
            return recorded
    return build_snapshot_dto(cluster_snapshot_id)


@router.delete("/cluster-snapshots/{cluster_snapshot_id}", status_code=204)
def delete_cluster_snapshot_endpoint(
    cluster_snapshot_id: uuid.UUID,
) -> None:
    """Delete a leaf cluster snapshot.

    The snapshot must have no child snapshots referencing it as a parent.
    Conversations currently pointing to the deleted snapshot are updated to
    point at its parent (or NULL for root snapshots).

    Args:
        cluster_snapshot_id: Cluster snapshot UUID to delete.

    Raises:
        ClusterSnapshotNotFound:  If the snapshot does not exist.
        SnapshotHasChildren:      If the snapshot still has child snapshots.
    """
    result = get_cluster_snapshot_with_clusters(cluster_snapshot_id)
    if result is None:
        raise ClusterSnapshotNotFound(cluster_snapshot_id)
    n_children = count_snapshot_children(cluster_snapshot_id)
    if n_children > 0:
        raise SnapshotHasChildren(cluster_snapshot_id)
    delete_cluster_snapshot(cluster_snapshot_id)
    log.info("cluster_snapshot_deleted", extra={"snapshot_id": str(cluster_snapshot_id)})


@router.get(
    "/cluster-snapshots/{cluster_snapshot_id}/clusters/{cluster_id}/members",
    response_model=list[ClusterMembershipDto],
)
def get_cluster_members_endpoint(
    cluster_snapshot_id: uuid.UUID,
    cluster_id: uuid.UUID,
) -> list[ClusterMembershipDto]:
    """Return all movie memberships for a cluster, ordered by descending probability.

    Validates that ``cluster_id`` belongs to ``cluster_snapshot_id`` before
    fetching memberships so callers cannot enumerate members of arbitrary clusters.

    Args:
        cluster_snapshot_id: Cluster snapshot UUID.
        cluster_id:          Cluster UUID within that snapshot.

    Returns:
        List of ``ClusterMembershipDto`` ordered by probability descending.

    Raises:
        ClusterSnapshotNotFound: If the snapshot does not exist.
        HTTPException(404):      If the cluster does not belong to the snapshot.
    """
    result = get_cluster_snapshot_with_clusters(cluster_snapshot_id)
    if result is None:
        raise ClusterSnapshotNotFound(cluster_snapshot_id)
    cluster_ids = {c.id for c in result.clusters}
    if cluster_id not in cluster_ids:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found in snapshot {cluster_snapshot_id}.")
    memberships = get_memberships(cluster_id)
    log.debug(
        "cluster_members_fetched",
        extra={"cluster_id": str(cluster_id), "snapshot_id": str(cluster_snapshot_id), "count": len(memberships)},
    )
    return [ClusterMembershipDto(movie_id=m.movie_id, probability=m.probability) for m in memberships]


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
    if _demo.is_replay_mode():
        recorded = _demo.get_recorded_snapshot_graph(str(conversation_id))
        if recorded is not None:
            return recorded

    snapshots = get_conversation_cluster_snapshots(conversation_id)
    dto = build_snapshot_graph_dto(snapshots)
    log.debug("cluster_snapshot_graph", extra={"conversation_id": str(conversation_id), "n_nodes": len(dto.cluster_snapshots)})
    return dto
