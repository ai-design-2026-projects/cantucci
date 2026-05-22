import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class OfflineResult:
    """
    Output of the offline embedding pipeline.
    Attributes:
        fused_embeddings: Float32 array of shape (n, dim), row-wise L2-normalized.
        umap_coords:      Float64 array of shape (n, 2) with (x, y) projections.
        cluster_ids:      Primary cluster index per movie (0-based, argmax of soft membership).
        cluster_probs:    Soft-membership probability of the primary cluster per movie.
        n_clusters:       Total number of clusters found.
    """
    fused_embeddings: np.ndarray
    umap_coords: np.ndarray
    cluster_ids: list[int]
    cluster_probs: list[float]
    n_clusters: int


def compute_offline_columns(
    movie_ids: list[int],
    text_embeddings: np.ndarray,
    review_embeddings: np.ndarray | None,
    trailer_embeddings: np.ndarray | None = None,
) -> OfflineResult:
    """
    Compute fused embeddings, UMAP 2D coordinates, and HDBSCAN cluster assignments.
    Pure computation — no DB access, no LLM calls. All parameters come from the
    active YAML config. Called from ``db/ingest.py`` after catalogue rows are loaded.
    Args:
        movie_ids:          TMDB IDs in row order (used only for logging).
        text_embeddings:    Float32 array of shape (n, dim), L2-normalized.
        review_embeddings:  Float32 array of shape (n, dim) with zero rows for movies
                            lacking reviews, or None to skip fusion.
        trailer_embeddings: Float32 array of shape (n, dim) with zero rows for movies
                            lacking trailers, or None to skip trailer fusion.

    Returns:
        ``OfflineResult`` with fused embeddings, UMAP 2D coords, and primary cluster
        assignments for every movie.
    """
    from umap import UMAP

    from backend.settings import get_settings
    from core.clustering import hdbscan_soft
    from core.fusion import fuse_batch

    cfg = get_settings()
    fusion_cfg = cfg.fusion
    base_cfg = cfg.clustering.base
    umap_cfg = cfg.umap

    log.info("offline_fuse", extra={"n_movies": len(movie_ids)})
    fused = fuse_batch(
        text_embeddings,
        review_embeddings,
        fusion_cfg.text_weight,
        fusion_cfg.review_weight,
        trailer_embeddings,
        fusion_cfg.trailer_weight,
    )

    log.info("offline_umap")
    reducer = UMAP(
        n_components=2,
        n_neighbors=umap_cfg.n_neighbors,
        min_dist=umap_cfg.min_dist,
        metric="cosine",
        random_state=cfg.split.seed,
    )
    coords: np.ndarray = reducer.fit_transform(fused)

    log.info("offline_cluster")
    result = hdbscan_soft(
        fused,
        min_cluster_size=base_cfg.min_cluster_size,
        min_samples=base_cfg.min_samples,
        cluster_selection_method=base_cfg.cluster_selection_method,
        cluster_selection_epsilon=base_cfg.cluster_selection_epsilon,
    )

    primary_idx = np.argmax(result.probabilities, axis=1)
    cluster_ids: list[int] = primary_idx.tolist()
    cluster_probs: list[float] = result.probabilities[
        np.arange(len(cluster_ids)), primary_idx
    ].tolist()

    log.info(
        "offline_complete",
        extra={"n_movies": len(movie_ids), "n_clusters": result.n_clusters},
    )
    return OfflineResult(
        fused_embeddings=fused,
        umap_coords=coords,
        cluster_ids=cluster_ids,
        cluster_probs=cluster_probs,
        n_clusters=result.n_clusters,
    )
