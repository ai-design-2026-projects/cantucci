import numpy as np

from backend.settings import UmapConfig


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
