"""Stub for the relevance scoring tool used by the Decision Agent."""

import logging
from uuid import UUID

from backend.models.clusters import ClusterSnapshot

log = logging.getLogger(__name__)


def score(
    user_query: str,
    clusters: list[ClusterSnapshot],
) -> dict[UUID, float]:
    """Return per-cluster relevance scores for *user_query* (not yet implemented).

    Args:
        user_query: Oracle's free-text message for the current turn.
        clusters:   Current cluster snapshots.

    Returns:
        Empty dict until the relevance scorer is wired in.
    """
    log.warning("relevance scorer not yet implemented")
    return {}
