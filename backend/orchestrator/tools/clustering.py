"""Stub for the Cluster Agent integration.

Will wrap the real Cluster Agent once it is implemented.
"""

import logging
from typing import Any

from backend.models.clusters import ClusterSnapshot

log = logging.getLogger(__name__)


def produce_clusters(
    candidates: list[Any],
    prev_clusters: list[ClusterSnapshot],
    feedback_history: list[Any],
) -> list[ClusterSnapshot]:
    """Return updated cluster snapshots for the current turn (not yet implemented).

    Args:
        candidates:       Candidate titles from the Retrieval System.
        prev_clusters:    Cluster snapshots from the previous turn.
        feedback_history: Accumulated oracle feedback entries.

    Returns:
        Empty list until the Cluster Agent is wired in.
    """
    log.warning("clustering not yet implemented")
    return []
