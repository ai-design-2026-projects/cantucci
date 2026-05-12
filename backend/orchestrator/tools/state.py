"""DB-backed state helpers for the Orchestrator.

Thin wrappers around ``backend.api.sessions`` and ``backend.api.retrieval``
so the Orchestrator itself never touches SQL directly.
"""

import logging
import uuid
from typing import Any

import backend.api.retrieval as api_retrieval
import backend.api.sessions as api_sessions
from backend.models.retrieval import TurnDetail

log = logging.getLogger(__name__)


def load_history(session_id: uuid.UUID) -> list[TurnDetail]:
    """Return all turns for a session in ascending turn_number order.

    Args:
        session_id: UUID of the session.

    Returns:
        Ordered list of TurnDetail objects.

    Raises:
        ValueError: If the session does not exist (propagated from get_session_full).
    """
    full = api_retrieval.get_session_full(session_id)
    return full.turns


def next_turn_number(session_id: uuid.UUID) -> int:
    """Return the 1-based index of the next turn for a session.

    Args:
        session_id: UUID of the session.

    Returns:
        len(history) + 1.
    """
    return len(load_history(session_id)) + 1


def record_turn(
    session_id: uuid.UUID,
    turn_number: int,
    user_message: str,
    assistant_message: str,
    step_type: str,
    converged: bool,
    turn_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Persist a completed turn and return its UUID.

    Args:
        session_id:        Parent session.
        turn_number:       1-based index within the session.
        user_message:      Oracle utterance.
        assistant_message: System response.
        step_type:         One of show | ask | stop.
        converged:         Whether this turn declared convergence.
        turn_id:           Pre-allocated UUID (used for LLM log correlation).
                           If None, the DB generates one.

    Returns:
        UUID of the persisted turn row.
    """
    return api_sessions.append_turn(
        session_id=session_id,
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=assistant_message,
        step_type=step_type,
        converged=converged,
        turn_id=turn_id,
    )


def declare_convergence(
    session_id: uuid.UUID,
    preference_profile: dict[str, Any],
) -> None:
    """Mark a session as converged and store the preference profile.

    Args:
        session_id:         Session to mark converged.
        preference_profile: Structured profile extracted from oracle feedback.
    """
    api_sessions.mark_converged(session_id, preference_profile)
