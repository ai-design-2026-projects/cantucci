import uuid
from typing import Any

from backend.data_access.cluster_snapshots.queries import (
    get_cluster_labels,
    get_cluster_snapshot_with_clusters,
    get_snapshot_members,
)
from backend.data_access.cluster_snapshots.types import ClusterSnapshotRow
from backend.exceptions import ClusterSnapshotNotFound
from backend.routers.dto.cluster_snapshots.dtos import (
    ClusterDto,
    ClusterSnapshotDto,
    ClusterSnapshotGraphDto,
    ClusterSnapshotGraphNodeDto,
    SnapshotMemberDto,
)


def build_snapshot_dto(cluster_snapshot_id: uuid.UUID) -> ClusterSnapshotDto:
    """Build a ClusterSnapshotDto from a snapshot id.

    Fetches the snapshot, its clusters, and the argmax member list in two
    queries. Does NOT call get_memberships per-cluster.

    Args:
        cluster_snapshot_id: UUID of the cluster snapshot to build.

    Returns:
        Populated ``ClusterSnapshotDto``.

    Raises:
        ClusterSnapshotNotFound: If the snapshot does not exist.
    """
    result = get_cluster_snapshot_with_clusters(cluster_snapshot_id)
    if result is None:
        raise ClusterSnapshotNotFound(cluster_snapshot_id)
    snapshot_members = get_snapshot_members(cluster_snapshot_id)
    cluster_dtos = [
        ClusterDto(
            id=c.id,
            label=c.label,
            summary=c.summary,
            exemplar_movie_ids=c.exemplar_movie_ids,
            parent_cluster_id=c.parent_cluster_id,
        )
        for c in result.clusters
    ]
    member_dtos = [
        SnapshotMemberDto(
            movie_id=m.movie_id,
            title=m.title,
            umap_x=m.umap_x,
            umap_y=m.umap_y,
            cluster_id=m.cluster_id,
            probability=m.probability,
        )
        for m in snapshot_members
    ]
    s = result.cluster_snapshot
    return ClusterSnapshotDto(
        id=s.id,
        parent_id=s.parent_id,
        operation=s.operation,
        params=s.params,
        config_hash=s.config_hash,
        clusters=cluster_dtos,
        members=member_dtos,
        created_at=s.created_at,
    )


def build_snapshot_graph_dto(snapshots: list[ClusterSnapshotRow]) -> ClusterSnapshotGraphDto:
    """Build a ClusterSnapshotGraphDto from a list of snapshot rows.

    Resolves cluster labels for any UUIDs referenced in snapshot params
    (``source_cluster_id`` for drill-down/focus, ``merged_cluster_ids`` for merge)
    in a single batch query, then assembles one typed node per snapshot.

    Args:
        snapshots: Ordered list of cluster snapshot rows for a conversation.

    Returns:
        Populated ``ClusterSnapshotGraphDto``.
    """
    all_ids = [cid for s in snapshots for cid in s.referenced_cluster_ids()]
    label_map = get_cluster_labels(all_ids) if all_ids else {}
    nodes = [
        ClusterSnapshotGraphNodeDto(
            id=s.id,
            parent_id=s.parent_id,
            operation=s.operation,
            created_at=s.created_at,
            params=s.params,
            resolved_cluster_labels={
                str(cid): label_map[cid]
                for cid in s.referenced_cluster_ids()
                if cid in label_map
            },
        )
        for s in snapshots
    ]
    return ClusterSnapshotGraphDto(cluster_snapshots=nodes)
