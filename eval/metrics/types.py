"""Metric result dataclasses for the evaluation harness."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClusteringMetrics:
    """Cluster-count metric from the final cluster snapshot.

    Attributes:
        final_num_clusters: Number of clusters in the snapshot.
    """
    final_num_clusters: int
