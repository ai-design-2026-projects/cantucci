import numpy as np


def cluster_entropy(probabilities: list[float]) -> float:
    """Compute Shannon entropy of a soft membership distribution.

    High entropy (→ log₂(n_clusters)) means the movie is uniformly spread
    across all clusters — high uncertainty. Zero entropy means deterministic
    assignment to a single cluster.

    Args:
        probabilities: Soft membership probabilities for one movie; need not sum to 1
                       (will be renormalized). Must be non-negative.

    Returns:
        Shannon entropy in nats, in [0, log(n_clusters)]. Returns 0.0 for empty input.
    """
    p = np.array(probabilities, dtype=np.float64)
    p = p[p > 0]
    if p.size == 0:
        return 0.0
    p = p / p.sum()
    return float(-np.sum(p * np.log(p)))
