import numpy as np

from core.clustering import SoftClusterResult, hdbscan_soft


def subcluster(
    embeddings: np.ndarray,
    min_cluster_size: int,
    min_samples: int,
) -> SoftClusterResult:
    """Run HDBSCAN soft clustering on a subset (drill-down or recut).

    Falls back to a reduced min_cluster_size when the subset is smaller than
    the requested minimum (minimum of 2 enforced).

    Args:
        embeddings:       Float32 array of shape (n, 1024), L2-normalized.
        min_cluster_size: Requested minimum cluster size.
        min_samples:      HDBSCAN min_samples.

    Returns:
        ``SoftClusterResult`` for the subset.
    """
    effective_min = max(2, min(min_cluster_size, embeddings.shape[0] // 5))
    effective_samples = max(1, min(min_samples, effective_min))
    return hdbscan_soft(
        embeddings,
        min_cluster_size=effective_min,
        min_samples=effective_samples,
    )
