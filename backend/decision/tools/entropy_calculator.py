"""Entropy calculator for the Decision Agent.

Computes the mean per-title Shannon entropy normalised to [0, 1] across
cluster soft-score distributions.  High entropy means titles are scattered
across clusters (ask); low entropy means clear dominant cluster (recommend).
"""

import logging
import math

log = logging.getLogger(__name__)


def compute(soft_scores: list[list[float]]) -> float:
    """Return mean normalised Shannon entropy over all title soft-score vectors.

    Each inner list is the soft-score vector for one title, one entry per cluster.
    Scores are normalised to a probability distribution before entropy is computed.

    Args:
        soft_scores: Per-title cluster probability lists. ``soft_scores[i][j]``
                     is title i's affinity for cluster j.  May be unnormalised.

    Returns:
        Mean entropy in [0, 1], where 0 = fully certain (one cluster dominates)
        and 1 = maximum uncertainty (uniform distribution).  Returns 0.0 when
        ``soft_scores`` is empty or there are fewer than 2 clusters.
    """
    if not soft_scores or len(soft_scores[0]) < 2:
        return 0.0

    n_clusters = len(soft_scores[0])
    log_n = math.log(n_clusters)
    total = 0.0

    for scores in soft_scores:
        s = sum(scores)
        if s <= 0:
            total += 1.0
            continue
        probs = [v / s for v in scores]
        h = -sum(p * math.log(p) for p in probs if p > 0)
        total += h / log_n

    return total / len(soft_scores)
