import logging
import uuid

from backend.agents.clustering.operations._helpers import exemplars
from backend.agents.clustering.types import ClusterDraft, ClusterSnapshotDraft
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters, get_memberships

log = logging.getLogger(__name__)


async def merge_clusters(
    cluster_ids: list[uuid.UUID],
    parent_cluster_snapshot_id: uuid.UUID,
    merged_label: str = "Merged",
) -> ClusterSnapshotDraft:
    """Merge multiple clusters into a single cluster, keeping the rest unchanged.

    Args:
        cluster_ids:                List of cluster UUIDs to merge.
        parent_cluster_snapshot_id: Cluster snapshot the clusters belong to.
        merged_label:               Label for the new merged cluster.

    Returns:
        ``ClusterSnapshotDraft`` with the merged cluster and all unchanged clusters.
    """
    cswc = get_cluster_snapshot_with_clusters(parent_cluster_snapshot_id)
    if cswc is None:
        raise ValueError(f"Cluster snapshot {parent_cluster_snapshot_id} not found")

    merge_set = set(cluster_ids)
    merged_memberships: dict[int, float] = {}
    unchanged: list[ClusterDraft] = []

    for cluster in cswc.clusters:
        if cluster.id in merge_set:
            for m in get_memberships(cluster.id):
                existing = merged_memberships.get(m.movie_id, 0.0)
                merged_memberships[m.movie_id] = max(existing, m.probability)
        else:
            members = [(m.movie_id, m.probability) for m in get_memberships(cluster.id)]
            unchanged.append(ClusterDraft(
                label=cluster.label,
                summary=cluster.summary,
                exemplar_movie_ids=cluster.exemplar_movie_ids,
                parent_cluster_id=cluster.parent_cluster_id,
                memberships=members,
            ))

    mids = list(merged_memberships.keys())
    prbs = [merged_memberships[m] for m in mids]
    merged_draft = ClusterDraft(
        label=merged_label,
        summary=None,
        exemplar_movie_ids=exemplars(mids, prbs),
        parent_cluster_id=None,
        memberships=list(merged_memberships.items()),
    )

    clusters = unchanged + [merged_draft]
    params: dict = {
        "operation": "merge",
        "merged_cluster_ids": [str(cid) for cid in cluster_ids],
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id),
    }
    log.info("merge_complete", extra={"n_merged": len(cluster_ids), "remaining_clusters": len(clusters)})
    return ClusterSnapshotDraft(operation="merge", params=params, clusters=clusters)
