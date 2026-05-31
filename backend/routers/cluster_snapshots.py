import logging
import uuid

from fastapi import APIRouter, HTTPException

from backend.data_access.cluster_snapshots.queries import (
    count_snapshot_children,
    delete_cluster_snapshot,
    get_cluster_snapshot_with_clusters,
    get_memberships,
)
from backend.exceptions import ClusterSnapshotNotFound, SnapshotHasChildren
from backend.routers.dto.cluster_snapshots.dtos import ClusterMembershipDto, ClusterSnapshotDto
from backend.routers.dto.cluster_snapshots.build_snapshot import build_snapshot_dto

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cluster-snapshots", tags=["cluster-snapshots"])


@router.get("/get/{cluster_snapshot_id}", response_model=ClusterSnapshotDto)
def get_cluster_snapshot_endpoint(cluster_snapshot_id: uuid.UUID) -> ClusterSnapshotDto:
    """Return a cluster snapshot with its full cluster list and argmax member counts.

    In demo replay mode, recorded snapshots are served from the manifest and no
    database query is issued.

    Args:
        cluster_snapshot_id: Cluster snapshot UUID.

    Returns:
        ``ClusterSnapshotDto`` with clusters, labels, and per-cluster argmax members.

    Raises:
        ClusterSnapshotNotFound: If the cluster snapshot does not exist.
    """
    return build_snapshot_dto(cluster_snapshot_id)


@router.delete("/delete/{cluster_snapshot_id}", status_code=204)
def delete_cluster_snapshot_endpoint(
    cluster_snapshot_id: uuid.UUID,
) -> None:
    """Delete a leaf cluster snapshot.

    The snapshot must have no child snapshots referencing it as a parent.
    Any conversations currently pointing to the deleted snapshot will have their
    ``current_cluster_snapshot_id`` set to its parent (or NULL for root-level snapshots).

    Args:
        cluster_snapshot_id: Cluster snapshot UUID to delete.

    Raises:
        ClusterSnapshotNotFound: If the snapshot does not exist.
        SnapshotHasChildren:     If the snapshot still has child snapshots referencing it.
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
    "/cluster_members/{cluster_snapshot_id}/{cluster_id}",
    response_model=list[ClusterMembershipDto],
)
def get_cluster_members_endpoint(
    cluster_snapshot_id: uuid.UUID,
    cluster_id: uuid.UUID,
) -> list[ClusterMembershipDto]:
    """Return all movie memberships for a cluster, ordered by descending soft-assignment probability.

    Validates that ``cluster_id`` belongs to ``cluster_snapshot_id`` before fetching
    memberships, preventing enumeration of arbitrary clusters across snapshots.

    Args:
        cluster_snapshot_id: Cluster snapshot UUID that owns the cluster.
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
