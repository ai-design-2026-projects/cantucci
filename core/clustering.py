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
    data: np.ndarray,
    min_cluster_size: int,
    min_samples: int,
    cluster_selection_method: str = "eom",
    cluster_selection_epsilon: float = 0.0,
    metric: str = "euclidean",
) -> SoftClusterResult:
    """
    Run HDBSCAN with soft membership vectors.

    Accepts either L2-normalised embedding vectors (``metric="euclidean"``) or
    a precomputed square distance matrix (``metric="precomputed"``). The
    precomputed path is the correct way to cluster when combining distances
    from multiple embedding spaces via ``core.fusion.combined_distance_matrix``.

    Noise points (label −1) have their soft membership spread uniformly across
    all clusters. When using a precomputed distance matrix, soft assignment
    falls back to hard labels (1.0 for the assigned cluster, uniform for noise)
    because HDBSCAN's ``all_points_membership_vectors`` requires an indexable
    metric.

    Args:
        data:                     For ``metric="euclidean"``: float32 (n, dim)
                                  L2-normalised embeddings. For
                                  ``metric="precomputed"``: float32 (n, n)
                                  symmetric distance matrix with values in
                                  [0, 2] (e.g. cosine distances).
        min_cluster_size:         HDBSCAN minimum cluster size.
        min_samples:              HDBSCAN min_samples (noise tolerance).
        cluster_selection_method: ``"eom"`` or ``"leaf"``.
        cluster_selection_epsilon: Distance threshold for cluster merging.
        metric:                   ``"euclidean"`` (default) or ``"precomputed"``.

    Returns:
        ``SoftClusterResult`` with labels, soft probability matrix, and cluster count.

    Raises:
        ValueError: If data array is empty or metric is unsupported.
        RuntimeError: If HDBSCAN finds zero clusters (all noise).
    """
    import hdbscan

    if data.shape[0] == 0:
        raise ValueError("data array is empty")
    if metric not in ("euclidean", "precomputed"):
        raise ValueError(f"Unsupported metric '{metric}'; use 'euclidean' or 'precomputed'")

    use_soft = metric != "precomputed"

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_method=cluster_selection_method,
        cluster_selection_epsilon=cluster_selection_epsilon,
        metric=metric,
        prediction_data=use_soft,
    )
    clusterer.fit(data)

    n_clusters = int(clusterer.labels_.max()) + 1
    if n_clusters == 0:
        raise RuntimeError(
            f"HDBSCAN found zero clusters (all noise) with "
            f"min_cluster_size={min_cluster_size}, min_samples={min_samples}. "
            "Reduce min_cluster_size or check the embedding quality."
        )

    n_points = data.shape[0]
    if use_soft:
        probs = hdbscan.all_points_membership_vectors(clusterer)
        probs = np.array(probs, dtype=np.float32)
    else:
        probs = np.zeros((n_points, n_clusters), dtype=np.float32)
        for i, label in enumerate(clusterer.labels_):
            if label >= 0:
                probs[i, label] = 1.0

    row_sums = probs.sum(axis=1, keepdims=True)
    zero_rows = (row_sums == 0).flatten()
    if zero_rows.any():
        probs[zero_rows] = 1.0 / n_clusters

    row_sums = probs.sum(axis=1, keepdims=True)
    probs = probs / row_sums

    log.info(
        "hdbscan_soft_complete",
        extra={
            "n_points": n_points,
            "n_clusters": n_clusters,
            "noise_points": int((clusterer.labels_ == -1).sum()),
            "metric": metric,
        },
    )
    return SoftClusterResult(labels=clusterer.labels_, probabilities=probs, n_clusters=n_clusters)
