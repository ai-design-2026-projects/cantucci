"""Deterministic recommendation renderer for the Orchestrator's presentation step.

Replaces the former LLM-based render step. No LLM calls are made here —
the reply is assembled from already-computed cluster and decision data, so
there is no extra token cost or latency on recommendation turns.
"""

import logging

from backend.api.types import ClusterSnapshot
from backend.decision.types import DecisionResult

log = logging.getLogger(__name__)


def render_recommendation(
    *,
    best_cluster: ClusterSnapshot,
    decision: DecisionResult,
    top_k: int,
) -> str:
    """Format a recommendation reply from the best cluster and decision rationale.

    Args:
        best_cluster: The cluster the Decision Agent chose to recommend.
        decision:     The Decision Agent's result for this turn, including the
                      rationale string.
        top_k:        Maximum number of top-scoring films to list.

    Returns:
        A markdown-formatted reply string ready to show the oracle.
    """
    top_assignments = sorted(
        [a for a in best_cluster.assignments if not a.excluded],
        key=lambda a: a.score,
        reverse=True,
    )[:top_k]

    film_lines = "\n".join(
        f"- {a.title or str(a.movie_id)}" for a in top_assignments
    )

    reply = (
        f"**{best_cluster.name}**\n\n"
        f"{best_cluster.description or ''}\n\n"
        f"*Why this fits:* {decision.rationale}\n\n"
        f"Top picks:\n{film_lines}"
    )

    log.debug(
        "deterministic render complete",
        extra={
            "cluster_name": best_cluster.name,
            "n_films": len(top_assignments),
        },
    )
    return reply
