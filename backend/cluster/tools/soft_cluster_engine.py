from dataclasses import dataclass
import logging
import warnings

import hdbscan
import numpy as np

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=ImportWarning, module="umap")
    from umap.umap_ import UMAP

from backend.settings import UmapConfig

log = logging.getLogger(__name__)


@dataclass
class SoftClusterResult:
    """Output of ``cluster()``.

    Attributes:
        labels:      1-D integer array; -1 means HDBSCAN classified as noise.
        membership:  2-D float array of shape (n_points, n_clusters) with soft
                     probabilities, or ``None`` when all points are noise.
        n_clusters:  Number of clusters found (excluding noise label -1).
    """

    labels: np.ndarray
    membership: np.ndarray | None
    n_clusters: int


def cluster(
    embeddings: np.ndarray,
    *,
    min_cluster_size: int,
    min_samples: int,
    cluster_selection_method: str = "eom",
    umap_cfg: UmapConfig | None = None,
    seed: int = 42,
    **_kwargs: object,
) -> SoftClusterResult:
    """
    Run UMAP (optional) + HDBSCAN soft clustering over *embeddings*.

    When ``umap_cfg`` is provided and ``umap_cfg.enabled`` is True, the
    embeddings are projected down to ``umap_cfg.n_components`` dimensions
    before HDBSCAN. This is critical for high-dim (>=100) inputs where
    HDBSCAN otherwise classifies most points as noise.

    Uses ``prediction_data=True`` so that ``all_points_membership_vectors``
    can produce overlapping cluster assignments.  The HDBSCAN metric is
    ``"euclidean"``; on UMAP output this matches UMAP's internal geometry,
    and on raw embeddings it is equivalent to cosine for unit-normalised
    vectors (the ingest pipeline guarantees normalisation).

    Args:
        embeddings:              Float32 array of shape (n_points, dim).
        min_cluster_size:        HDBSCAN ``min_cluster_size`` (from config).
        min_samples:             HDBSCAN ``min_samples`` (from config).
        cluster_selection_method: ``"eom"`` (default) or ``"leaf"``.
        umap_cfg:                UMAP pre-reduction config. ``None`` or
                                 ``enabled=False`` skips reduction.
        seed:                    RNG seed for UMAP reproducibility.
        **_kwargs:               Extra config keys are silently ignored so
                                 callers can pass the full config dict.

    Returns:
        ``SoftClusterResult`` with ``membership=None`` when n_clusters == 0.

    Raises:
        ValueError: If *embeddings* has fewer than 2 points.
    """
    if embeddings.shape[0] < 2:
        raise ValueError(
            f"clustering requires at least 2 points, got {embeddings.shape[0]}"
        )

    cluster_input: np.ndarray = embeddings
    n_neighbors_used: int | None = None
    
    # Run UMAP pre-reduction when enabled
    if umap_cfg is not None and umap_cfg.enabled:
        n_points = embeddings.shape[0]
        # UMAP requires n_neighbors <= n_points - 1 and at least n_components + 2
        # points to produce a meaningful embedding; below that we skip reduction.
        if n_points >= max(umap_cfg.n_components + 2, 4):
            n_neighbors_used = min(umap_cfg.n_neighbors, n_points - 1)
            reducer = UMAP(
                n_components=umap_cfg.n_components,
                n_neighbors=n_neighbors_used,
                min_dist=umap_cfg.min_dist,
                metric=umap_cfg.metric,
                random_state=seed,
                # Set explicitly: UMAP forces n_jobs=1 when random_state is given,
                # and warns about it unless we acknowledge by setting n_jobs=1 here.
                n_jobs=1,
            )
            # UMAP's fit_transform returns float64 by default; downcast to float32 for HDBSCAN.
            cluster_input = reducer.fit_transform(embeddings).astype(np.float32)
            log.debug(
                "soft_cluster_engine umap reduction",
                extra={
                    "n_points": n_points,
                    "input_dim": int(embeddings.shape[1]),
                    "reduced_dim": umap_cfg.n_components,
                    "n_neighbors_used": n_neighbors_used,
                },
            )
        else:
            log.debug(
                "soft_cluster_engine umap skipped (pool too small)",
                extra={
                    "n_points": n_points,
                    "n_components": umap_cfg.n_components,
                },
            )

    # Run HDBSCAN on the reduced or raw embeddings
    clusterer = hdbscan.HDBSCAN(
        metric="euclidean",
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        prediction_data=True,
        cluster_selection_method=cluster_selection_method,
    )
    labels: np.ndarray = clusterer.fit_predict(cluster_input)
    n_clusters = int(labels.max()) + 1 if labels.max() >= 0 else 0

    if n_clusters == 0:
        log.warning(
            "soft_cluster_engine: all points classified as noise",
            extra={"n_points": embeddings.shape[0], "n_clusters": 0},
        )
        return SoftClusterResult(labels=labels, membership=None, n_clusters=0)

    membership: np.ndarray = hdbscan.all_points_membership_vectors(clusterer)

    log.debug(
        "soft_cluster_engine complete",
        extra={
            "n_points": embeddings.shape[0],
            "n_clusters": n_clusters,
            "noise_count": int((labels == -1).sum()),
            "reduced_dim": int(cluster_input.shape[1]),
        },
    )
    return SoftClusterResult(labels=labels, membership=membership, n_clusters=n_clusters)
