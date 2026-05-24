import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class OfflineResult:
    """
    Output of the offline embedding pipeline.
    Attributes:
        umap_coords:      Float64 array of shape (n, 2) with (x, y) projections.
        cluster_ids:      Primary cluster index per movie (0-based, argmax of soft membership).
        cluster_probs:    Soft-membership probability of the primary cluster per movie.
        n_clusters:       Total number of clusters found.
    """
    umap_coords: np.ndarray
    cluster_ids: list[int]
    cluster_probs: list[float]
    n_clusters: int


def compute_offline_columns(
    movie_ids: list[int],
    text_embeddings: np.ndarray,
    review_embeddings: np.ndarray | None,
) -> OfflineResult:
    """
    Compute UMAP 2D coordinates and HDBSCAN cluster assignments from BGE embeddings.

    Fuses text and review embeddings (both in BGE space) in memory, then runs
    two independent UMAP passes and HDBSCAN:

    1. **Clustering UMAP** (``umap.clustering_n_components`` dimensions, default 50):
       reduces the curse of dimensionality before HDBSCAN.
    2. **HDBSCAN** on the reduced vectors.
    3. **Visualization UMAP** (2D): projects the original fused vectors to (x, y)
       for the cluster map; independent of the clustering pass.

    The fused vector is never stored in the DB — only the UMAP 2D coordinates and
    cluster assignments are persisted. For multi-modal clustering that mixes
    incompatible embedding spaces (e.g. BGE text + CLIP trailer), use
    ``core.fusion.combined_distance_matrix`` at runtime instead.

    Pure computation — no DB access, no LLM calls. All parameters come from the
    active YAML config. Called from ``db/ingest.py`` after catalogue rows are
    loaded.

    Args:
        movie_ids:         TMDB IDs in row order (used only for logging).
        text_embeddings:   Float32 array of shape (n, dim), L2-normalized.
        review_embeddings: Float32 array of shape (n, dim) with zero rows for
                           movies lacking reviews, or None to use text only.

    Returns:
        ``OfflineResult`` with UMAP 2D coords and primary cluster assignments.
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
    )

    log.info("offline_umap_clustering", extra={"n_components": umap_cfg.clustering_n_components})
    reducer_clust = UMAP(
        n_components=umap_cfg.clustering_n_components,
        n_neighbors=umap_cfg.clustering_n_neighbors,
        min_dist=umap_cfg.clustering_min_dist,
        metric="cosine",
        random_state=cfg.split.seed,
    )
    fused_reduced: np.ndarray = reducer_clust.fit_transform(fused).astype(np.float32)

    log.info("offline_cluster")
    result = hdbscan_soft(
        fused_reduced,
        min_cluster_size=base_cfg.min_cluster_size,
        min_samples=base_cfg.min_samples,
        cluster_selection_method=base_cfg.cluster_selection_method,
        cluster_selection_epsilon=base_cfg.cluster_selection_epsilon,
    )

    log.info("offline_umap_visualization")
    reducer_viz = UMAP(
        n_components=2,
        n_neighbors=umap_cfg.n_neighbors,
        min_dist=umap_cfg.min_dist,
        metric="cosine",
        random_state=cfg.split.seed,
    )
    coords: np.ndarray = reducer_viz.fit_transform(fused)

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
        umap_coords=coords,
        cluster_ids=cluster_ids,
        cluster_probs=cluster_probs,
        n_clusters=result.n_clusters,
    )
