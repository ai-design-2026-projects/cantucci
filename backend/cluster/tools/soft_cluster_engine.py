"""soft_cluster_engine — HDBSCAN soft clustering over candidate embeddings.

Returns per-film cluster probability distributions so downstream consumers can
build overlapping cluster memberships (e.g. a film may be 70% "Cyberpunk Noir"
and 30% "Existential Drama").
"""

from dataclasses import dataclass

import hdbscan
import numpy as np

import logging

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
    **_kwargs: object,
) -> SoftClusterResult:
    """Run HDBSCAN soft clustering over *embeddings*.

    Uses ``prediction_data=True`` so that ``all_points_membership_vectors``
    can produce overlapping cluster assignments.  Embeddings must already be
    unit-normalised (all-MiniLM-L6-v2 ingest guarantees this), making
    Euclidean distance equivalent to cosine distance in ordering.

    Args:
        embeddings:              Float32 array of shape (n_points, dim).
        min_cluster_size:        HDBSCAN ``min_cluster_size`` (from config).
        min_samples:             HDBSCAN ``min_samples`` (from config).
        cluster_selection_method: ``"eom"`` (default) or ``"leaf"``.
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

    clusterer = hdbscan.HDBSCAN(
        metric="euclidean",
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        prediction_data=True,
        cluster_selection_method=cluster_selection_method,
    )
    labels: np.ndarray = clusterer.fit_predict(embeddings)
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
        },
    )
    return SoftClusterResult(labels=labels, membership=membership, n_clusters=n_clusters)
