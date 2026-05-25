import logging
import uuid

from backend.agents.clustering.operations._helpers import exemplars
from backend.agents.clustering.types import ClusterDraft, ClusterSnapshotDraft
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters, get_memberships
from backend.settings import get_settings

log = logging.getLogger(__name__)


async def focus(
    source_cluster_id: uuid.UUID,
    parent_cluster_snapshot_id: uuid.UUID,
) -> ClusterSnapshotDraft:
    """Narrow the working set to a single cluster, discarding all other points.

    Produces a snapshot containing exactly one cluster — the selected cluster's
    members under its existing label. All other clusters in the parent snapshot
    are dropped. No HDBSCAN or LLM call is made.

    A follow-up ``recut`` or ``drill_down`` on the resulting snapshot will
    operate only on the focused subset.

    Args:
        source_cluster_id:          Cluster to keep.
        parent_cluster_snapshot_id: Snapshot the cluster belongs to.

    Returns:
        ``ClusterSnapshotDraft`` with a single cluster.

    Raises:
        ValueError: If the source cluster has no members or is not found in the snapshot.
    """
    cswc = get_cluster_snapshot_with_clusters(parent_cluster_snapshot_id)
    if cswc is None:
        raise ValueError(f"Cluster snapshot {parent_cluster_snapshot_id} not found")

    source = next((c for c in cswc.clusters if c.id == source_cluster_id), None)
    if source is None:
        raise ValueError(f"Cluster {source_cluster_id} not found in snapshot {parent_cluster_snapshot_id}")

    memberships_rows = get_memberships(source_cluster_id)
    if not memberships_rows:
        raise ValueError(f"Cluster {source_cluster_id} has no members")

    cfg = get_settings()
    members = [(m.movie_id, m.probability) for m in memberships_rows]
    mids = [m[0] for m in members]
    prbs = [m[1] for m in members]

    cluster = ClusterDraft(
        label=source.label or "Focused",
        summary=source.summary,
        exemplar_movie_ids=exemplars(mids, prbs, cfg.labeling.top_exemplars),
        parent_cluster_id=source_cluster_id,
        memberships=members,
    )

    params: dict = {
        "operation": "focus",
        "source_cluster_id": str(source_cluster_id),
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id),
    }
    log.info("focus_complete", extra={"source_cluster_id": str(source_cluster_id), "n_members": len(members)})
    return ClusterSnapshotDraft(operation="focus", params=params, clusters=[cluster])
