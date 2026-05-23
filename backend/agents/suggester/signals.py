import uuid

import numpy as np

from backend.data_access.cluster_snapshots.types import ClusterMembershipRow, ClusterRow


def compute_cluster_centroids(
    clusters: list[ClusterRow],
    text_embeddings_by_movie: dict[int, list[float]],
) -> dict[uuid.UUID, np.ndarray]:
    """Compute an L2-normalised centroid for each cluster from its exemplar embeddings.

    Clusters whose exemplars have no embeddings in ``text_embeddings_by_movie`` are
    silently omitted from the result.

    Mirrors the exemplar-mean recipe in ``backend/agents/concept/parser.py:76-80``.

    Args:
        clusters:                  Current cluster list.
        text_embeddings_by_movie:  Map of movie_id → raw embedding vector (from
                                   ``data_access.movies.queries.fetch_text_embeddings``).

    Returns:
        Dict mapping cluster UUID to its L2-normalised mean exemplar embedding.
    """
    centroids: dict[uuid.UUID, np.ndarray] = {}
    for cluster in clusters:
        vecs = [
            np.array(text_embeddings_by_movie[mid], dtype=np.float32)
            for mid in cluster.exemplar_movie_ids
            if mid in text_embeddings_by_movie
        ]
        if not vecs:
            continue
        centroid = np.mean(vecs, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        centroids[cluster.id] = centroid.astype(np.float32)
    return centroids


def find_similar_pairs(
    centroids: dict[uuid.UUID, np.ndarray],
    distance_max: float,
) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
    """Return cluster pairs whose cosine distance is below ``distance_max``.

    Cosine distance = 1 - dot(a, b) for L2-normalised vectors; range [0, 2].
    Results are sorted ascending by distance (most similar first).

    Args:
        centroids:    Map of cluster UUID → L2-normalised centroid.
        distance_max: Upper bound on cosine distance to include a pair.

    Returns:
        List of (cluster_id_a, cluster_id_b, distance) triples, sorted ascending.
    """
    ids = list(centroids.keys())
    pairs: list[tuple[uuid.UUID, uuid.UUID, float]] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            dist = float(1.0 - np.dot(centroids[a], centroids[b]))
            if dist < distance_max:
                pairs.append((a, b, dist))
    pairs.sort(key=lambda t: t[2])
    return pairs


def find_dominant_cluster(
    memberships_by_cluster: dict[uuid.UUID, list[ClusterMembershipRow]],
    dominance_fraction: float,
) -> uuid.UUID | None:
    """Return the cluster that holds more than ``dominance_fraction`` of all members.

    Args:
        memberships_by_cluster: Map of cluster UUID → membership rows.
        dominance_fraction:     Threshold fraction in (0, 1).

    Returns:
        UUID of the dominant cluster, or None if no cluster exceeds the threshold.
    """
    total = sum(len(rows) for rows in memberships_by_cluster.values())
    if total == 0:
        return None
    for cluster_id, rows in memberships_by_cluster.items():
        if len(rows) / total > dominance_fraction:
            return cluster_id
    return None


def find_noise_fraction(
    memberships_by_cluster: dict[uuid.UUID, list[ClusterMembershipRow]],
    n_clusters: int,
) -> float:
    """Estimate the fraction of members that are likely HDBSCAN noise points.

    HDBSCAN noise points are assigned to their argmax cluster with near-uniform
    probability (~1/n_clusters). Members with probability < 2/n_clusters are
    counted as noise proxies.

    Args:
        memberships_by_cluster: Map of cluster UUID → membership rows.
        n_clusters:             Total number of clusters (used to compute the threshold).

    Returns:
        Fraction of total memberships identified as noise proxies (0.0 if n_clusters < 2).
    """
    if n_clusters < 2:
        return 0.0
    threshold = 2.0 / n_clusters
    total = 0
    noisy = 0
    for rows in memberships_by_cluster.values():
        for row in rows:
            total += 1
            if row.probability < threshold:
                noisy += 1
    return noisy / total if total > 0 else 0.0
