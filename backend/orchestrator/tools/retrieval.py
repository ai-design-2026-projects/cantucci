"""Stub for the Retrieval System integration.

Will wrap the real Retrieval agent once it is implemented.
Signature mirrors architecture.md §Retrieval interface.
"""

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class CandidateTitle:
    """A single retrieval candidate returned by the Retrieval System."""

    movie_id: int
    title: str
    score: float


def search_candidates(
    query: str,
    k: int,
    active_constraints: dict,  # type: ignore[type-arg]
) -> list[CandidateTitle]:
    """Return ranked candidate titles matching *query* (not yet implemented).

    Args:
        query:              Free-text query derived from oracle preferences.
        k:                  Maximum number of candidates to return.
        active_constraints: Oracle-stated hard constraints (exclude, require, etc.).

    Returns:
        Empty list until the Retrieval System is wired in.
    """
    log.warning("retrieval not yet implemented")
    return []
