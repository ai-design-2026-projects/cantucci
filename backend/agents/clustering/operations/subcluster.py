import numpy as np

from core.clustering import SoftClusterResult, hdbscan_soft


def subcluster(
    embeddings: np.ndarray | None,
    min_cluster_size: int,
    min_samples: int,
    distance_matrix: np.ndarray | None = None,
) -> SoftClusterResult:
    """Run HDBSCAN soft clustering on a subset (drill-down or recut).

    Accepts either L2-normalised embedding vectors or a precomputed square
    distance matrix (from ``core.fusion.combined_distance_matrix``). Exactly
    one of *embeddings* or *distance_matrix* must be provided.

    Falls back to a reduced min_cluster_size when the subset is smaller than
    the requested minimum (minimum of 2 enforced).

    Args:
        embeddings:       Float32 (n, dim) L2-normalised embeddings. Pass
                          ``None`` when providing *distance_matrix*.
        min_cluster_size: Requested minimum cluster size.
        min_samples:      HDBSCAN min_samples.
        distance_matrix:  Float32 (n, n) precomputed symmetric distance matrix.
                          Pass ``None`` when providing *embeddings*.

    Returns:
        ``SoftClusterResult`` for the subset.

    Raises:
        ValueError: If both or neither of *embeddings* / *distance_matrix* are
                    provided.
    """
    if (embeddings is None) == (distance_matrix is None):
        raise ValueError("Exactly one of embeddings or distance_matrix must be provided")

    data = embeddings if embeddings is not None else distance_matrix
    n = data.shape[0]  # type: ignore[union-attr]
    effective_min = max(2, min(min_cluster_size, n // 5))
    effective_samples = max(1, min(min_samples, effective_min))

    metric = "euclidean" if distance_matrix is None else "precomputed"
    return hdbscan_soft(
        data,
        min_cluster_size=effective_min,
        min_samples=effective_samples,
        metric=metric,
    )
