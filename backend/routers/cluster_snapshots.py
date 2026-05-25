import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.types import User
from backend.data_access.cluster_snapshots.queries import (
    count_snapshot_children,
    delete_cluster_snapshot,
    get_cluster_snapshot_with_clusters,
    get_conversation_cluster_snapshots,
    get_memberships,
    get_root_cluster_snapshot,
)
from backend.exceptions import ClusterSnapshotNotFound, NotFoundError, SnapshotHasChildren
from backend.routers.auth_deps import get_current_user
from backend.routers.dto.cluster_snapshots.dtos import ClusterDto, ClusterMembershipDto, ClusterSnapshotDto, ClusterSnapshotGraphDto

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
    result = get_cluster_snapshot_with_clusters(root.id)
    if result is None:
        raise ClusterSnapshotNotFound(root.id)
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


@router.delete("/cluster-snapshots/{cluster_snapshot_id}", status_code=204)
def delete_cluster_snapshot_endpoint(
    cluster_snapshot_id: uuid.UUID,
    user: Annotated[User | None, Depends(get_current_user)],
) -> None:
    """Delete a leaf cluster snapshot.

    The snapshot must have no child snapshots referencing it as a parent.
    Conversations currently pointing to the deleted snapshot are updated to
    point at its parent (or NULL for root snapshots).

    Args:
        cluster_snapshot_id: Cluster snapshot UUID to delete.
        user:                Authenticated user. Anonymous callers receive 401.

    Raises:
        HTTPException(401):       If the request is anonymous.
        ClusterSnapshotNotFound:  If the snapshot does not exist.
        SnapshotHasChildren:      If the snapshot still has child snapshots.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    result = get_cluster_snapshot_with_clusters(cluster_snapshot_id)
    if result is None:
        raise ClusterSnapshotNotFound(cluster_snapshot_id)
    n_children = count_snapshot_children(cluster_snapshot_id)
    if n_children > 0:
        raise SnapshotHasChildren(cluster_snapshot_id)
    delete_cluster_snapshot(cluster_snapshot_id)
    log.info("cluster_snapshot_deleted", extra={"snapshot_id": str(cluster_snapshot_id), "user_id": str(user.id)})


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
