"""Orchestrator-facing retrieval tool — thin bridge to the Retrieval System.

Converts a RetrievalResult into the CandidateTitle list that the Orchestrator
and Cluster Agent consume. Keeps the Orchestrator's import surface stable while
the Retrieval System evolves independently.
"""

import logging
from dataclasses import dataclass

from backend.retrieval import agent as retrieval_agent

log = logging.getLogger(__name__)


@dataclass
class CandidateTitle:
    """A single retrieval candidate as seen by the Orchestrator."""

    movie_id: int
    title: str
    score: float


def search_candidates(
    query: str,
    k: int,
    active_constraints: dict,  # type: ignore[type-arg]
) -> list[CandidateTitle]:
    """Return ranked candidate titles matching *query*.

    Delegates to the Retrieval System agent and maps the result to the
    CandidateTitle type used by the Orchestrator.

    Args:
        query:              Free-text query derived from oracle preferences.
        k:                  Maximum number of candidates to return.
        active_constraints: Oracle-stated hard constraints (passed through;
                            not yet applied in the Retrieval System).

    Returns:
        List of CandidateTitle in descending similarity order.
    """
    result = retrieval_agent.retrieve(
        query=query,
        k=k,
        active_constraints=active_constraints or None,
    )

    return [
        CandidateTitle(
            movie_id=m.movie_id,
            title=m.title,
            score=result.scores.get(m.movie_id, 0.0),
        )
        for m in result.candidates
    ]
