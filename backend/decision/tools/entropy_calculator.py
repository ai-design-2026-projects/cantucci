"""Stub for the entropy calculation tool used by the Decision Agent."""

import logging

log = logging.getLogger(__name__)


def compute(soft_scores: list[list[float]]) -> float:
    """Return the entropy across cluster soft-score distributions (not yet implemented).

    Args:
        soft_scores: Per-cluster lists of assignment soft scores.

    Returns:
        0.0 until the entropy calculator is wired in.
    """
    log.warning("entropy calculator not yet implemented")
    return 0.0
