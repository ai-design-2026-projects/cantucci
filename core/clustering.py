import logging
from dataclasses import dataclass
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class SoftClusterResult:
    """
    Output of HDBSCAN soft clustering.
    Attributes:
        labels:       Hard cluster label per point (−1 = noise before soft assignment).
        probabilities: Soft membership matrix of shape (n_points, n_clusters).
                       Each row sums to 1.0 (after noise redistribution).
        n_clusters:   Number of clusters found (excluding noise).
    """
    labels: np.ndarray
    probabilities: np.ndarray
    n_clusters: int


def hdbscan_soft(
    embeddings: np.ndarray,
    min_cluster_size: int,
    min_samples: int,
    cluster_selection_method: str = "eom",
    cluster_selection_epsilon: float = 0.0,
) -> SoftClusterResult:
    """
    Run HDBSCAN with soft membership vectors on L2-normalized embeddings.
    
    Noise points (label −1) have their soft membership spread across nearest
    clusters via ``hdbscan.all_points_membership_vectors``.
    Args:
        embeddings:               Float32 array of shape (n, 1024), L2-normalized.
        min_cluster_size:         HDBSCAN minimum cluster size.
        min_samples:              HDBSCAN min_samples (noise tolerance).
        cluster_selection_method: ``"eom"`` or ``"leaf"``.
        cluster_selection_epsilon: Distance threshold for cluster merging.
    Returns:
        ``SoftClusterResult`` with labels, soft probability matrix, and cluster count.
    Raises:
        ValueError: If embeddings array is empty.
        RuntimeError: If HDBSCAN finds zero clusters (all noise).
    """
    import hdbscan

    if embeddings.shape[0] == 0:
        raise ValueError("embeddings array is empty")

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_method=cluster_selection_method,
        cluster_selection_epsilon=cluster_selection_epsilon,
        metric="euclidean",
        prediction_data=True,
    )
    clusterer.fit(embeddings)

    n_clusters = int(clusterer.labels_.max()) + 1
    if n_clusters == 0:
        raise RuntimeError(
            f"HDBSCAN found zero clusters (all noise) with "
            f"min_cluster_size={min_cluster_size}, min_samples={min_samples}. "
            "Reduce min_cluster_size or check the embedding quality."
        )

    probs = hdbscan.all_points_membership_vectors(clusterer)
    probs = np.array(probs, dtype=np.float32)

    row_sums = probs.sum(axis=1, keepdims=True)
    zero_rows = (row_sums == 0).flatten()
    if zero_rows.any():
        probs[zero_rows] = 1.0 / n_clusters

    row_sums = probs.sum(axis=1, keepdims=True)
    probs = probs / row_sums

    log.info(
        "hdbscan_soft_complete",
        extra={
            "n_points": embeddings.shape[0],
            "n_clusters": n_clusters,
            "noise_points": int((clusterer.labels_ == -1).sum()),
        },
    )
    return SoftClusterResult(labels=clusterer.labels_, probabilities=probs, n_clusters=n_clusters)
