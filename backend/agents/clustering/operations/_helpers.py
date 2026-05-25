import numpy as np

from backend.settings import UmapConfig
from core.clustering import SoftClusterResult, hdbscan_soft

def reduce_for_clustering(embeddings: np.ndarray, umap_cfg: UmapConfig, seed: int) -> np.ndarray:
    """Apply UMAP dimensionality reduction before HDBSCAN clustering.

    Runs only when ``embeddings.shape[0] >= umap_cfg.clustering_min_dataset_size``.
    Below that threshold the original embeddings are returned unchanged — running
    UMAP on very small subsets produces unstable layouts and offers no quality
    benefit for HDBSCAN.

    Args:
        embeddings: Float32 (n, dim) L2-normalised embedding matrix.
        umap_cfg:   UMAP configuration section from the active settings.
        seed:       Random seed for reproducibility.

    Returns:
        Float32 (n, clustering_n_components) reduced array, or the original
        array unchanged when n is below the minimum dataset size.
    """
    n = embeddings.shape[0]
    if n < umap_cfg.clustering_min_dataset_size:
        return embeddings

    from umap import UMAP

    reducer = UMAP(
        n_components=umap_cfg.clustering_n_components,
        n_neighbors=umap_cfg.clustering_n_neighbors,
        min_dist=umap_cfg.clustering_min_dist,
        metric="cosine",
        random_state=seed,
    )
    return reducer.fit_transform(embeddings).astype(np.float32)


def exemplars(movie_ids: list[int], probs: list[float], n: int) -> list[int]:
    """Return the top-n movie IDs by descending probability.

    Args:
        movie_ids: TMDB integer IDs.
        probs:     Corresponding membership probabilities.
        n:         Maximum number of exemplars to return (from ``cfg.labeling.top_exemplars``).

    Returns:
        List of movie IDs sorted by descending probability, truncated to ``n``.
    """
    paired = sorted(zip(probs, movie_ids), reverse=True)
    return [mid for _, mid in paired[:n]]

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
