"""Lexical relevance scorer for the Decision Agent.

Scores each cluster against the oracle's query using Jaccard overlap of
lowercased alphanumeric token sets.  This is a deterministic MVP heuristic;
embedding-based scoring is a planned follow-up.
"""

import logging
import re
from uuid import UUID

from backend.models.clusters import ClusterSnapshot

log = logging.getLogger(__name__)


def _tokens(text: str) -> set[str]:
    """Return lowercase alphanumeric token set from *text*."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def score(
    user_query: str,
    clusters: list[ClusterSnapshot],
) -> dict[UUID, float]:
    """Return per-cluster Jaccard relevance scores for *user_query*.

    Args:
        user_query: Oracle's free-text message for the current turn.
        clusters:   Current cluster snapshots.

    Returns:
        Dict mapping cluster id to Jaccard score in [0, 1].  Empty dict when
        *clusters* is empty.
    """
    if not clusters:
        return {}

    query_tokens = _tokens(user_query)
    if not query_tokens:
        return {c.id: 0.0 for c in clusters}

    result: dict[UUID, float] = {}
    for c in clusters:
        cluster_text = f"{c.name} {c.description or ''}"
        cluster_tokens = _tokens(cluster_text)
        if not cluster_tokens:
            result[c.id] = 0.0
        else:
            intersection = len(query_tokens & cluster_tokens)
            union = len(query_tokens | cluster_tokens)
            result[c.id] = intersection / union

    return result
