from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from backend.agents.intent.types import PartitionBin
from backend.data_access.movies.types import NumericStats
from backend.settings import UmapConfig
from core.clustering import SoftClusterResult, hdbscan_soft

if TYPE_CHECKING:
    from backend.agents.intent.types import Modality

log = logging.getLogger(__name__)


def resolve_movie_ids(
    source_cluster_id: uuid.UUID | None,
    movie_ids: list[int] | None,
    parent_cluster_snapshot_id: uuid.UUID | None,
) -> list[int]:
    """Resolve the input movie set for a clustering operation.

    Resolution order:
    1. ``source_cluster_id`` → members of that cluster.
    2. ``movie_ids`` → explicit list.
    3. ``parent_cluster_snapshot_id`` → union of all movies across that snapshot's clusters.
    4. No arguments → full catalogue.

    Args:
        source_cluster_id:          Cluster whose members form the input; takes priority.
        movie_ids:                  Explicit list; used when ``source_cluster_id`` is ``None``.
        parent_cluster_snapshot_id: Snapshot from which to union all movies; used when
                                    both ``source_cluster_id`` and ``movie_ids`` are ``None``.

    Returns:
        List of TMDB movie IDs in the resolved input set.

    Raises:
        ValueError: If ``source_cluster_id`` is set but has no members, or the referenced
                    snapshot is not found.
    """
    from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters, get_memberships
    from backend.data_access.movies.queries import list_movie_ids

    if source_cluster_id is not None:
        memberships = get_memberships(source_cluster_id)
        if not memberships:
            raise ValueError(f"Cluster {source_cluster_id} has no members")
        return [m.movie_id for m in memberships]
    if movie_ids is not None:
        return movie_ids
    if parent_cluster_snapshot_id is not None:
        cswc = get_cluster_snapshot_with_clusters(parent_cluster_snapshot_id)
        if cswc is None:
            raise ValueError(f"Cluster snapshot {parent_cluster_snapshot_id} not found")
        seen: set[int] = set()
        result: list[int] = []
        for cluster in cswc.clusters:
            for m in get_memberships(cluster.id):
                if m.movie_id not in seen:
                    seen.add(m.movie_id)
                    result.append(m.movie_id)
        return result
    return list_movie_ids()


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


@dataclass(frozen=True, slots=True)
class _AttrSpec:
    """Per-attribute configuration for bin edge selection and label generation."""

    candidates: list[float]
    fmt: Callable[[float], str]
    all_label: str
    two: tuple[str, str]
    three: tuple[str, str, str]


_SPECS: dict[str, _AttrSpec] = {
    "runtime": _AttrSpec(
        candidates=[45.0, 60.0, 75.0, 90.0, 105.0, 120.0, 135.0, 150.0, 180.0, 210.0],
        fmt=lambda v: str(int(v)),
        all_label="All films",
        two=("Short (<{e} min)", "Long (≥{e} min)"),
        three=("Short (<{lo} min)", "Medium ({lo}–{hi} min)", "Long (≥{hi} min)"),
    ),
    "release_year": _AttrSpec(
        candidates=[1940.0, 1950.0, 1960.0, 1970.0, 1980.0, 1990.0, 2000.0, 2010.0, 2020.0],
        fmt=lambda v: str(int(v)),
        all_label="All films",
        two=("Before {e}", "{e}–present"),
        three=("Before {lo}", "{lo}–{hi}", "{hi}–present"),
    ),
    "vote_average": _AttrSpec(
        candidates=[4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5],
        fmt=lambda v: f"{v:.1f}",
        all_label="All films",
        two=("Below average (<{e})", "Above average (≥{e})"),
        three=("Low (<{lo})", "Average ({lo}–{hi})", "Acclaimed (≥{hi})"),
    ),
}


def _select_edges(stats: NumericStats, candidates: list[float]) -> list[float]:
    """Return up to 2 edges from candidates, snapped to the p25/p75 positions of the distribution.

    Only candidates strictly between the data min and max are considered, so edges
    always produce non-empty bins. Duplicate snapped values are dropped, which may
    yield 0 or 1 edge when the distribution is very narrow.
    """
    lo = stats.min_val if stats.min_val is not None else candidates[0]
    hi = stats.max_val if stats.max_val is not None else candidates[-1]
    valid = [c for c in candidates if lo < c < hi]
    if not valid:
        return []
    targets = [v for v in (stats.p25, stats.p75) if v is not None]
    if not targets:
        targets = [v for v in (stats.p50,) if v is not None]
    edges: list[float] = []
    for target in targets:
        nearest = min(valid, key=lambda c: abs(c - target))
        if nearest not in edges:
            edges.append(nearest)
    return sorted(edges)


def _build_bins(spec: _AttrSpec, edges: list[float]) -> list[PartitionBin]:
    """Build labelled PartitionBin objects from the selected edge values."""
    if not edges:
        return [PartitionBin(label=spec.all_label, min=None, max=None)]
    if len(edges) == 1:
        e = spec.fmt(edges[0])
        lo_label, hi_label = spec.two
        return [
            PartitionBin(label=lo_label.format(e=e), min=None, max=edges[0]),
            PartitionBin(label=hi_label.format(e=e), min=edges[0], max=None),
        ]
    lo_f, hi_f = spec.fmt(edges[0]), spec.fmt(edges[1])
    lo_label, mid_label, hi_label = spec.three
    return [
        PartitionBin(label=lo_label.format(lo=lo_f, hi=hi_f), min=None, max=edges[0]),
        PartitionBin(label=mid_label.format(lo=lo_f, hi=hi_f), min=edges[0], max=edges[1]),
        PartitionBin(label=hi_label.format(lo=lo_f, hi=hi_f), min=edges[1], max=None),
    ]


def propose_bins(attribute: str, stats: NumericStats) -> list[PartitionBin]:
    """Propose labelled bins for a numeric partition attribute using the data distribution.

    Bins are selected deterministically: for each attribute a fixed set of
    round-number candidate edges is defined; edges are chosen by snapping the p25
    and p75 positions of the actual distribution to the nearest candidate, then
    labelled with human-friendly strings.

    Args:
        attribute: Partition attribute name — one of ``"runtime"``,
                   ``"release_year"``, or ``"vote_average"``.
        stats:     Distribution statistics for the attribute within the in-scope
                   movie set.

    Returns:
        Ordered list of ``PartitionBin`` objects ready to pass to ``partition_by``
        after user confirmation.

    Raises:
        ValueError: If *attribute* is not a supported numeric attribute.
    """
    if attribute not in _SPECS:
        raise ValueError(
            f"Unsupported numeric attribute '{attribute}'. Valid: {sorted(_SPECS)}"
        )

    spec = _SPECS[attribute]
    edges = _select_edges(stats, spec.candidates)
    bins = _build_bins(spec, edges)

    log.info(
        "partition_advisor_proposed",
        extra={
            "attribute": attribute,
            "n_bins": len(bins),
            "bin_labels": [b.label for b in bins],
        },
    )
    return bins


@dataclass(frozen=True, slots=True)
class _EmbeddingContext:
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


def load_embeddings(resolved_movie_ids: list[int], embedding_spaces: list[Modality]) -> _EmbeddingContext:
    """Fetch embeddings for the resolved movie set and return a bundled context.

    For single-modality TEXT requests only the text embedding map is fetched.
    For multi-modal requests all specified modalities are fetched and movies
    lacking any one modality are excluded.

    Args:
        resolved_movie_ids: Movie IDs whose embeddings should be loaded.
        embedding_spaces:   Modalities to load.

    Returns:
        ``_EmbeddingContext`` with available IDs, emb_map, and raw modal data.

    Raises:
        ValueError: If no embeddings are found for the resolved set.
    """
    from backend.agents.intent.types import Modality as _Modality
    from backend.data_access.movies.queries import fetch_modality_embeddings, fetch_text_embeddings

    if len(embedding_spaces) == 1 and embedding_spaces[0] == _Modality.TEXT:
        emb_map = fetch_text_embeddings(resolved_movie_ids)
        available_ids = [mid for mid in resolved_movie_ids if mid in emb_map]
        return _EmbeddingContext(
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
    return _EmbeddingContext(
        available_ids=available_ids,
        emb_map=emb_map,
        multi_modal=True,
        modal_data=modal_data,
        embedding_spaces=embedding_spaces,
    )


def cluster_group(
    group_ids: list[int],
    emb_ctx: _EmbeddingContext,
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
