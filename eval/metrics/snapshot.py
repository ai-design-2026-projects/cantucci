"""Cluster-snapshot-level deterministic metrics for the evaluation harness."""
import logging
import uuid

from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters

log = logging.getLogger(__name__)


def compute_num_clusters(snapshot_id: uuid.UUID) -> int:
    """Return the number of clusters in the given snapshot.

    Args:
        snapshot_id: UUID of the cluster snapshot to measure.

    Returns:
        Final cluster count; returns ``0`` when the snapshot is not found.
    """
    snapshot_with_clusters = get_cluster_snapshot_with_clusters(snapshot_id)
    if snapshot_with_clusters is None:
        return 0
    num_clusters = len(snapshot_with_clusters.clusters)
    log.debug(
        "clustering_metrics_computed",
        extra={"snapshot_id": str(snapshot_id), "num_clusters": num_clusters},
    )
    return num_clusters
