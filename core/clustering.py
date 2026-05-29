import logging
from dataclasses import dataclass
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class SoftClusterResult:
    """
    Output of HDBSCAN soft clustering.
    Attributes:
        labels:       Hard cluster label per point (−1 = noise before soft assignment).
        probabilities: Soft membership matrix of shape (n_points, n_clusters).
                       Each row sums to 1.0 (after noise redistribution).
        n_clusters:   Number of clusters found (excluding noise).
    """
    labels: np.ndarray
    probabilities: np.ndarray
    n_clusters: int


def _fit_soft(
    data: np.ndarray,
    min_cluster_size: int,
    min_samples: int,
    cluster_selection_method: str,
    cluster_selection_epsilon: float,
    metric: str,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Fit HDBSCAN with zero-cluster retry and return normalised soft memberships.

    Retries up to three times, halving ``min_cluster_size`` and ``min_samples``
    on each attempt, when HDBSCAN finds zero clusters (all noise).  The soft
    membership matrix is renormalised so every row sums to 1.0, with noise
    points receiving a uniform distribution across all clusters.

    Args:
        data:                      Float32 (n, dim) L2-normalised embeddings for
                                   ``metric="euclidean"``, or float32 (n, n)
                                   symmetric distance matrix for
                                   ``metric="precomputed"``.
        min_cluster_size:          Requested HDBSCAN minimum cluster size; may be
                                   reduced internally on zero-cluster retry.
        min_samples:               Requested HDBSCAN min_samples; may be reduced
                                   internally on zero-cluster retry.
        cluster_selection_method:  ``"eom"`` or ``"leaf"``.
        cluster_selection_epsilon: Distance threshold for cluster merging.
        metric:                    ``"euclidean"`` or ``"precomputed"``.

    Returns:
        Tuple ``(labels, probs, n_clusters)``:
        - ``labels``:     Int array (n,) of hard cluster assignments as produced
                          by HDBSCAN (−1 for noise points before redistribution).
        - ``probs``:      Float32 (n, n_clusters) row-normalised soft memberships
                          with noise rows redistributed uniformly.
        - ``n_clusters``: Number of non-noise clusters found.

    Raises:
        RuntimeError: If HDBSCAN finds zero clusters after all retry attempts.
    """
    import hdbscan as hdbscan_lib

    use_soft = metric != "precomputed"
    current_mcs = min_cluster_size
    current_mss = min_samples
    max_attempts = 3
    clusterer = None
    n_clusters = 0

    for attempt in range(max_attempts):
        clusterer = hdbscan_lib.HDBSCAN(
            min_cluster_size=current_mcs,
            min_samples=current_mss,
            cluster_selection_method=cluster_selection_method,
            cluster_selection_epsilon=cluster_selection_epsilon,
            metric=metric,
            prediction_data=use_soft,
        )
        clusterer.fit(data)
        n_clusters = int(clusterer.labels_.max()) + 1
        if n_clusters > 0:
            break
        if attempt < max_attempts - 1:
            log.warning(
                "hdbscan_all_noise_retry",
                extra={
                    "attempt": attempt + 1,
                    "min_cluster_size": current_mcs,
                    "min_samples": current_mss,
                },
            )
            current_mcs = max(2, current_mcs // 2)
            current_mss = max(1, current_mss // 2)

    if n_clusters == 0:
        raise RuntimeError(
            f"HDBSCAN found zero clusters (all noise) after {max_attempts} attempts; "
            f"final min_cluster_size={current_mcs}, min_samples={current_mss}."
        )

    assert clusterer is not None
    n_points = data.shape[0]

    if use_soft:
        probs = hdbscan_lib.all_points_membership_vectors(clusterer)
        probs = np.array(probs, dtype=np.float32)
    else:
        probs = np.zeros((n_points, n_clusters), dtype=np.float32)
        for i, label in enumerate(clusterer.labels_):
            if label >= 0:
                probs[i, label] = 1.0

    row_sums = probs.sum(axis=1, keepdims=True)
    zero_rows = (row_sums == 0).flatten()
    if zero_rows.any():
        probs[zero_rows] = 1.0 / n_clusters

    row_sums = probs.sum(axis=1, keepdims=True)
    probs = probs / row_sums

    return clusterer.labels_, probs, n_clusters


def _merge_to_k(
    data: np.ndarray,
    probs: np.ndarray,
    k: int,
    metric: str,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Merge the nearest cluster pair until exactly k clusters remain.

    Soft-membership columns are summed on each merge so rows continue to
    sum to 1.0 after renormalisation.  The nearest pair is identified by
    prob-weighted centroid distance (``metric="euclidean"``) or average-
    linkage over hard-assigned members (``metric="precomputed"``).

    Args:
        data:   Float32 (n, dim) embedding array or (n, n) symmetric distance
                matrix — the same array that was passed to HDBSCAN.  Used only
                to measure inter-cluster distance, not re-fitted.
        probs:  Float32 (n, C) soft-membership matrix with C > k; rows sum to 1.
        k:      Target number of clusters after merging.
        metric: ``"euclidean"`` — nearest pair by prob-weighted centroid L2
                distance; ``"precomputed"`` — nearest pair by average-linkage
                over hard-assigned members read from the distance matrix.

    Returns:
        Tuple ``(labels, probs, n_clusters)`` where ``n_clusters == k``.
    """
    probs = probs.copy()
    n_clusters = probs.shape[1]

    while n_clusters > k:
        if metric == "euclidean":
            # Prob-weighted centroid for each cluster column
            centroids = (probs.T @ data.astype(np.float32)) / probs.sum(axis=0).reshape(-1, 1)
            diff = centroids[:, np.newaxis, :] - centroids[np.newaxis, :, :]
            dist = np.sqrt((diff ** 2).sum(axis=-1))
            np.fill_diagonal(dist, np.inf)
        else:
            # Average-linkage over hard-assigned members using the distance matrix
            hard = probs.argmax(axis=1)
            dist = np.full((n_clusters, n_clusters), np.inf)
            for ci in range(n_clusters):
                for cj in range(ci + 1, n_clusters):
                    idx_i = np.where(hard == ci)[0]
                    idx_j = np.where(hard == cj)[0]
                    if idx_i.size > 0 and idx_j.size > 0:
                        avg = float(data[np.ix_(idx_i, idx_j)].mean())
                        dist[ci, cj] = avg
                        dist[cj, ci] = avg

        row, col = np.unravel_index(int(dist.argmin()), dist.shape)
        i, j = int(row), int(col)

        merged_col = probs[:, i] + probs[:, j]
        keep = [c for c in range(n_clusters) if c not in (i, j)]
        probs = np.concatenate([probs[:, keep], merged_col.reshape(-1, 1)], axis=1)

        row_sums = probs.sum(axis=1, keepdims=True)
        probs = probs / row_sums

        n_clusters = probs.shape[1]

    labels = probs.argmax(axis=1).astype(np.intp)
    return labels, probs, n_clusters


def hdbscan_soft(
    data: np.ndarray,
    min_cluster_size: int,
    min_samples: int,
    cluster_selection_method: str = "eom",
    cluster_selection_epsilon: float = 0.0,
    metric: str = "euclidean",
    target_n_clusters: int | None = None,
) -> SoftClusterResult:
    """
    Run HDBSCAN with soft membership vectors.

    Accepts either L2-normalised embedding vectors (``metric="euclidean"``) or
    a precomputed square distance matrix (``metric="precomputed"``). The
    precomputed path is the correct way to cluster when combining distances
    from multiple embedding spaces via ``core.fusion.combined_distance_matrix``.

    Noise points (label −1) have their soft membership spread uniformly across
    all clusters. When using a precomputed distance matrix, soft assignment
    falls back to hard labels (1.0 for the assigned cluster, uniform for noise)
    because HDBSCAN's ``all_points_membership_vectors`` requires an indexable
    metric.

    When ``target_n_clusters`` is set the function attempts to return exactly
    that many clusters:

    * If HDBSCAN's emergent count exceeds the target, the nearest cluster pair
      is merged (summing their soft-probability columns) repeatedly until the
      target is reached.  Rows remain normalised to 1.0 throughout.
    * If HDBSCAN's emergent count is below the target, the function re-fits
      with progressively smaller ``min_cluster_size`` and ``cluster_selection_method="leaf"``
      (which over-segments), up to four additional attempts.  If the data
      cannot support the requested count even at the floor params, a WARNING is
      logged and the best achievable count is returned.

    Args:
        data:                     For ``metric="euclidean"``: float32 (n, dim)
                                  L2-normalised embeddings. For
                                  ``metric="precomputed"``: float32 (n, n)
                                  symmetric distance matrix with values in
                                  [0, 2] (e.g. cosine distances).
        min_cluster_size:         HDBSCAN minimum cluster size.
        min_samples:              HDBSCAN min_samples (noise tolerance).
        cluster_selection_method: ``"eom"`` or ``"leaf"``.
        cluster_selection_epsilon: Distance threshold for cluster merging.
        metric:                   ``"euclidean"`` (default) or ``"precomputed"``.
        target_n_clusters:        Optional target cluster count (>= 2).  When
                                  ``None`` (default) the emergent HDBSCAN count
                                  is returned unchanged, preserving the existing
                                  behaviour.

    Returns:
        ``SoftClusterResult`` with labels, soft probability matrix, and cluster count.

    Raises:
        ValueError: If data array is empty, metric is unsupported, or
                    ``target_n_clusters`` is set to a value less than 2.
        RuntimeError: If HDBSCAN finds zero clusters (all noise) after up to three
                      attempts, each halving ``min_cluster_size`` and ``min_samples``.
    """
    if data.shape[0] == 0:
        raise ValueError("data array is empty")
    if metric not in ("euclidean", "precomputed"):
        raise ValueError(f"Unsupported metric '{metric}'; use 'euclidean' or 'precomputed'")
    if target_n_clusters is not None and target_n_clusters < 2:
        raise ValueError(f"target_n_clusters must be >= 2, got {target_n_clusters}")

    initial_labels, probs, n_clusters = _fit_soft(
        data, min_cluster_size, min_samples, cluster_selection_method, cluster_selection_epsilon, metric
    )

    if target_n_clusters is not None and n_clusters < target_n_clusters:
        expand_mcs = min_cluster_size
        expand_mss = min_samples
        max_expand_attempts = 4
        for _ in range(max_expand_attempts):
            expand_mcs = max(2, expand_mcs // 2)
            expand_mss = max(1, expand_mss // 2)
            try:
                _, candidate_probs, candidate_n = _fit_soft(
                    data, expand_mcs, expand_mss, "leaf", cluster_selection_epsilon, metric
                )
            except RuntimeError:
                break
            if candidate_n > n_clusters:
                probs = candidate_probs
                n_clusters = candidate_n
            if n_clusters >= target_n_clusters:
                break
        if n_clusters < target_n_clusters:
            log.warning(
                "hdbscan_target_n_clusters_not_reached",
                extra={"target_n_clusters": target_n_clusters, "achieved": n_clusters},
            )

    merged = False
    if target_n_clusters is not None and n_clusters > target_n_clusters:
        _, probs, n_clusters = _merge_to_k(data, probs, target_n_clusters, metric)
        merged = True

    labels = probs.argmax(axis=1).astype(np.intp)
    n_points = data.shape[0]

    log.info(
        "hdbscan_soft_complete",
        extra={
            "n_points": n_points,
            "n_clusters": n_clusters,
            "noise_points": int((initial_labels == -1).sum()),
            "metric": metric,
            "min_cluster_size": min_cluster_size,
            "min_samples": min_samples,
            "target_n_clusters": target_n_clusters,
            "merged": merged,
        },
    )
    return SoftClusterResult(labels=labels, probabilities=probs, n_clusters=n_clusters)
