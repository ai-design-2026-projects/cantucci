import logging
import uuid

from backend.agents.clustering.operations._helpers import exemplars
from backend.agents.clustering.types import ClusterDraft, ClusterSnapshotDraft
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters, get_snapshot_members
from backend.settings import get_settings

log = logging.getLogger(__name__)


async def exclude_cluster(
    source_cluster_id: uuid.UUID,
    parent_cluster_snapshot_id: uuid.UUID,
) -> ClusterSnapshotDraft:
    """Remove one cluster from the working set, keeping all other clusters intact.

    The inverse of ``focus``: produces a snapshot containing every cluster in the
    parent snapshot *except* the selected one.  All other clusters retain their
    existing labels, summaries, and memberships.  No HDBSCAN or LLM call is made.

    Args:
        source_cluster_id:          Cluster to discard.
        parent_cluster_snapshot_id: Snapshot the cluster belongs to.

    Returns:
        ``ClusterSnapshotDraft`` with all clusters except the excluded one.

    Raises:
        ValueError: If the source cluster is not found, if the snapshot is not found,
                    or if the source is the only cluster (nothing would remain).
    """
    cswc = get_cluster_snapshot_with_clusters(parent_cluster_snapshot_id)
    if cswc is None:
        raise ValueError(f"Cluster snapshot {parent_cluster_snapshot_id} not found")

    source = next((c for c in cswc.clusters if c.id == source_cluster_id), None)
    if source is None:
        raise ValueError(f"Cluster {source_cluster_id} not found in snapshot {parent_cluster_snapshot_id}")

    remaining = [c for c in cswc.clusters if c.id != source_cluster_id]
    if not remaining:
        raise ValueError(f"Cannot exclude the only cluster in snapshot {parent_cluster_snapshot_id}")

    cfg = get_settings()
    all_members = get_snapshot_members(parent_cluster_snapshot_id)

    drafts: list[ClusterDraft] = []
    for cluster in remaining:
        memberships_rows = [(m.movie_id, m.probability) for m in all_members if m.cluster_id == cluster.id]
        mids = [m[0] for m in memberships_rows]
        prbs = [m[1] for m in memberships_rows]
        drafts.append(
            ClusterDraft(
                label=cluster.label,
                summary=cluster.summary,
                exemplar_movie_ids=exemplars(mids, prbs, cfg.labeling.top_exemplars),
                parent_cluster_id=cluster.id,
                memberships=memberships_rows,
            )
        )

    params: dict = {
        "operation": "exclude",
        "source_cluster_id": str(source_cluster_id),
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id),
    }
    log.info(
        "exclude_complete",
        extra={
            "source_cluster_id": str(source_cluster_id),
            "n_remaining": len(drafts),
        },
    )
    return ClusterSnapshotDraft(operation="exclude", params=params, clusters=drafts)
