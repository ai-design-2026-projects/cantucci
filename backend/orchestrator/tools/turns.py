"""Canned turn emitters for orchestrator bypass paths.

These functions handle turns where the normal pipeline (retrieval → cluster →
decision → ambiguity → render) is skipped. They write directly to the DB via
the api layer and return a TurnResult ready for the HTTP response.

No LLM calls, no DB reads — they are pure side-effecting writers.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

import backend.api.sessions as api_sessions
from backend.api.types import StepType
from backend.state.types import StateDecision
from backend.routers.dtos import TurnResult

log = logging.getLogger(__name__)


def emit_early_clarification(
    *,
    session_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
) -> TurnResult:
    """Persist and return a canned clarifying reply when retrieval yields no candidates.

    Args:
        session_id:   UUID of the target session.
        turn_id:      Pre-allocated turn UUID.
        turn_number:  1-based index for this turn.
        user_message: Oracle's message that produced empty retrieval.

    Returns:
        A TurnResult with step_type=ask and the canned reply.
    """
    reply = (
        "I couldn't find films matching that description. "
        "Could you tell me more about the kind of films you're looking for? "
        "For example, a mood, a director's style, a genre, or an era?"
    )
    step_type = StepType.ask
    api_sessions.append_turn(
        session_id=session_id,
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=reply,
        step_type=step_type.value,
        converged=False,
        turn_id=turn_id,
    )
    api_sessions.write_feedback(
        session_id=session_id,
        turn_id=turn_id,
        feedback_level="global",
        feedback_type="constraint",
        content=user_message,
        target_id=None,
    )
    log.warning(
        "no clusters returned — canned clarification turn",
        extra={"session_id": str(session_id), "turn_number": turn_number},
    )
    now = datetime.now(timezone.utc)
    return TurnResult(
        turn_id=turn_id,
        session_id=session_id,
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=reply,
        step_type=step_type,
        converged=False,
        created_at=now,
    )


def emit_drift_clarification(
    *,
    session_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
    decision: StateDecision,
) -> TurnResult:
    """Persist and return a drift-clarification turn.

    The LLM gate detected a preference contradiction. The normal pipeline
    (retrieval, cluster, decision, ambiguity, render) is bypassed. The reply
    asks the oracle to resolve the contradiction. A resolve_drift feedback
    row is written so that subsequent turns can detect this state.

    Args:
        session_id:   UUID of the target session.
        turn_id:      Pre-allocated turn UUID.
        turn_number:  1-based index for this turn.
        user_message: Oracle's message that triggered drift detection.
        decision:     StateDecision from check_llm_state.

    Returns:
        A TurnResult with step_type=ask, converged=False.
    """
    reply = (
        decision.reply
        or "I noticed a possible contradiction in your preferences — could you clarify?"
    )
    step_type = StepType.ask
    api_sessions.append_turn(
        session_id=session_id,
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=reply,
        step_type=step_type.value,
        converged=False,
        turn_id=turn_id,
    )
    api_sessions.write_feedback(
        session_id=session_id,
        turn_id=turn_id,
        feedback_level="global",
        feedback_type="resolve_drift",
        content=user_message,
        target_id=None,
    )
    log.warning(
        "drift clarification emitted",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "drift_topic": decision.drift_topic,
            "prior_statement": decision.prior_statement,
            "current_statement": decision.current_statement,
        },
    )
    log.info(
        "turn handled",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "step_type": step_type.value,
            "converged": False,
        },
    )
    now = datetime.now(timezone.utc)
    return TurnResult(
        turn_id=turn_id,
        session_id=session_id,
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=reply,
        step_type=step_type,
        converged=False,
        created_at=now,
    )
