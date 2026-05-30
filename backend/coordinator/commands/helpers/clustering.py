from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from backend.settings import UmapConfig
from core.clustering import SoftClusterResult, hdbscan_soft

if TYPE_CHECKING:
    from backend.agents.intent.types import Modality

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmbeddingContext:
    """Resolved embeddings and availability data for a set of movies.

    Attributes:
        available_ids:    Movie IDs that have embeddings in all requested spaces.
        emb_map:          Text embedding map (movie_id → vector); used for concept scoring and single-modal clustering.
        multi_modal:      True when more than one embedding space was requested.
        modal_data:       Per-modality embedding dicts; non-empty only when ``multi_modal`` is True.
        embedding_spaces: The modalities that were loaded.
    """

    available_ids: list[int]
    emb_map: dict
    multi_modal: bool
    modal_data: dict
    embedding_spaces: list[Modality]


def load_embeddings(resolved_movie_ids: list[int], embedding_spaces: list[Modality]) -> EmbeddingContext:
    """Fetch embeddings for the resolved movie set and return a bundled context.

    For single-modality TEXT requests only the text embedding map is fetched.
    For multi-modal requests all specified modalities are fetched and movies
    lacking any one modality are excluded.

    Args:
        resolved_movie_ids: Movie IDs whose embeddings should be loaded.
        embedding_spaces:   Modalities to load.

    Returns:
        ``EmbeddingContext`` with available IDs, emb_map, and raw modal data.

    Raises:
        ValueError: If no embeddings are found for the resolved set.
    """
    from backend.agents.intent.types import Modality as _Modality
    from backend.data_access.movies.queries import fetch_modality_embeddings, fetch_text_embeddings

    if len(embedding_spaces) == 1 and embedding_spaces[0] == _Modality.TEXT:
        emb_map = fetch_text_embeddings(resolved_movie_ids)
        available_ids = [mid for mid in resolved_movie_ids if mid in emb_map]
        return EmbeddingContext(
            available_ids=available_ids,
            emb_map=emb_map,
            multi_modal=False,
            modal_data={},
            embedding_spaces=embedding_spaces,
        )

    space_keys = [s.value for s in embedding_spaces]
    modal_data = fetch_modality_embeddings(resolved_movie_ids, space_keys)
    available_ids = [
        mid for mid in resolved_movie_ids
        if all(mid in modal_data[m] for m in space_keys)
    ]
    emb_map = {mid: modal_data["text"][mid].tolist() for mid in available_ids if "text" in modal_data}
    return EmbeddingContext(
        available_ids=available_ids,
        emb_map=emb_map,
        multi_modal=True,
        modal_data=modal_data,
        embedding_spaces=embedding_spaces,
    )


def cluster_group(
    group_ids: list[int],
    emb_ctx: EmbeddingContext,
    target_n_clusters: int | None = None,
) -> SoftClusterResult:
    """Cluster a group of movies using the given embedding context.

    Dispatches to multi-modal (precomputed distance matrix) or single-modal
    (UMAP + HDBSCAN) based on ``emb_ctx.multi_modal``.

    Args:
        group_ids:         Movie IDs to cluster (must be a subset of ``emb_ctx.available_ids``).
        emb_ctx:           Embedding context produced by ``load_embeddings``.
        target_n_clusters: Optional exact cluster count requested by the Oracle.
                           Forwarded to ``subcluster`` / ``hdbscan_soft``.

    Returns:
        ``SoftClusterResult`` for the group.
    """
    from backend.settings import get_settings
    from core.fusion import combined_distance_matrix

    cfg = get_settings()
    if emb_ctx.multi_modal:
        embs_by_modality = {
            space.value: np.array(
                [emb_ctx.modal_data[space.value][mid] for mid in group_ids], dtype=np.float32
            )
            for space in emb_ctx.embedding_spaces
        }
        dist_mat = combined_distance_matrix(embs_by_modality, cfg.fusion.runtime_weights)
        return subcluster(
            None,
            cfg.clustering.online.min_cluster_size,
            distance_matrix=dist_mat,
            cluster_selection_epsilon=cfg.clustering.online.cluster_selection_epsilon,
            target_n_clusters=target_n_clusters,
        )
    group_embs = np.array([emb_ctx.emb_map[mid] for mid in group_ids], dtype=np.float32)
    group_embs = reduce_for_clustering(group_embs, cfg.umap, cfg.split.seed)
    return subcluster(
        group_embs,
        cfg.clustering.online.min_cluster_size,
        cluster_selection_epsilon=cfg.clustering.online.cluster_selection_epsilon,
        target_n_clusters=target_n_clusters,
    )


def reduce_for_clustering(
    embeddings: np.ndarray,
    umap_cfg: UmapConfig,
    seed: int,
    metric: str = "cosine",
) -> np.ndarray:
    """Apply UMAP dimensionality reduction before HDBSCAN clustering.

    Three tiers based on dataset size:

    * ``n >= clustering_min_dataset_size``: full reduction to
      ``clustering_n_components`` dimensions.
    * ``n >= 2 * clustering_n_neighbors``: light reduction to
      ``min(n // 3, 20)`` dimensions — reduces the curse of dimensionality
      on small subsets without the instability of a full UMAP run.
    * ``n < 2 * clustering_n_neighbors``: embeddings returned unchanged —
      too few points for UMAP to be reliable.

    Args:
        embeddings: Float32 (n, dim) L2-normalised embedding matrix, or float32
                    (n, n) precomputed distance matrix when ``metric="precomputed"``.
        umap_cfg:   UMAP configuration section from the active settings.
        seed:       Random seed for reproducibility.
        metric:     Distance metric for UMAP — ``"cosine"`` (default) for embedding
                    vectors, ``"precomputed"`` for a square distance matrix. The
                    reduced output is always a euclidean coordinate array regardless
                    of the input metric.

    Returns:
        Float32 reduced array of shape (n, k), or the original array when n is
        too small for UMAP. When the original array is returned and
        ``metric="precomputed"``, the caller should detect this via shape equality
        with the input and fall back to precomputed HDBSCAN.
    """
    from umap import UMAP

    n = embeddings.shape[0]
    min_for_light = 2 * umap_cfg.clustering_n_neighbors

    if n >= umap_cfg.clustering_min_dataset_size:
        n_components = umap_cfg.clustering_n_components
    elif n >= min_for_light:
        n_components = max(2, min(n // 3, 20))
    else:
        return embeddings

    reducer = UMAP(
        n_components=n_components,
        n_neighbors=umap_cfg.clustering_n_neighbors,
        min_dist=umap_cfg.clustering_min_dist,
        metric=metric,
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


def adaptive_min_cluster_size(n: int) -> int:
    """Compute a population-relative min_cluster_size for HDBSCAN sub-clustering.

    Scales with population size so small sub-sets remain sensitive and large
    ones do not over-fragment.  Formula: ``max(5, n // 10)``.

    Args:
        n: Number of items in the sub-population to cluster.

    Returns:
        Recommended ``min_cluster_size`` for HDBSCAN.
    """
    return max(5, n // 10)


def subcluster(
    embeddings: np.ndarray | None,
    min_cluster_size: int,
    distance_matrix: np.ndarray | None = None,
    cluster_selection_epsilon: float = 0.0,
    target_n_clusters: int | None = None,
) -> SoftClusterResult:
    """Run HDBSCAN soft clustering on a cluster subset.

    Accepts either L2-normalised embedding vectors or a precomputed square
    distance matrix (from ``core.fusion.combined_distance_matrix``). Exactly
    one of *embeddings* or *distance_matrix* must be provided.

    ``min_cluster_size`` is capped at ``n // 5`` so that small subsets always
    produce at least a few clusters. ``min_samples`` is derived as
    ``max(1, effective_min // 3)``, which is more conservative than a fixed
    value of 1 and produces better-shaped clusters on dense subsets.

    Args:
        embeddings:                Float32 (n, dim) L2-normalised embeddings.
                                   Pass ``None`` when providing *distance_matrix*.
        min_cluster_size:          Requested minimum cluster size; capped
                                   adaptively based on subset size.
        distance_matrix:           Float32 (n, n) precomputed symmetric distance
                                   matrix. Pass ``None`` when providing *embeddings*.
        cluster_selection_epsilon: Distance threshold for merging very close
                                   clusters in the HDBSCAN condensed tree.
        target_n_clusters:         Optional target cluster count (>= 2).  When set,
                                   ``hdbscan_soft`` will merge or expand to reach
                                   exactly this many clusters.  ``None`` preserves
                                   the emergent HDBSCAN count.

    Returns:
        ``SoftClusterResult`` for the subset.

    Raises:
        ValueError: If both or neither of *embeddings* / *distance_matrix* are
                    provided.
    """
    if (embeddings is None) == (distance_matrix is None):
        raise ValueError("Exactly one of embeddings or distance_matrix must be provided")

    data = (embeddings if embeddings is not None else distance_matrix).astype(np.float64)
    n = data.shape[0]
    effective_min = max(2, min(min_cluster_size, n // 5))
    effective_samples = max(1, effective_min // 3)

    metric = "euclidean" if distance_matrix is None else "precomputed"
    return hdbscan_soft(
        data,
        min_cluster_size=effective_min,
        min_samples=effective_samples,
        cluster_selection_epsilon=cluster_selection_epsilon,
        metric=metric,
        target_n_clusters=target_n_clusters,
    )
