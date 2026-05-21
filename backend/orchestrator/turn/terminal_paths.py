"""Canned turn emitters for orchestrator bypass / terminal paths.

Everything here handles a turn that does NOT go through the normal pipeline
(retrieval → cluster → decision → render). Four shapes:

* ``terminate_turn``            — hard limit reached (max_turns or cost cap).
* ``natural_end_turn``          — state agent classified the message as a
                                  natural session close.
* ``emit_drift_clarification``  — state agent detected a preference
                                  contradiction; ask the oracle to clarify.
* ``emit_early_clarification``  — retrieval / clustering returned no
                                  candidates on the first turn; ask the oracle
                                  to be more concrete.

All four are sync — the orchestrator hops into a thread when calling them
from the async path. They write directly to the DB via ``api_sessions`` and
return a ``TurnDto`` ready for the HTTP response.

Only the natural-end and drift paths write ``oracle_feedback`` rows; those
are the rows downstream consumers (state agent's drift-state lookup,
convergence detection) actually read.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

import backend.repository.sessions as api_sessions
from backend.orchestrator.domain import StepType
from backend.profile.types import UserProfile
from backend.routers.dto.sessions.dtos import RecommendationDto, TurnDto
from backend.state.types import StateDecision

log = logging.getLogger(__name__)


def terminate_turn(
    *,
    session_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
    decision: StateDecision,
    recommendation: RecommendationDto | None = None,
) -> TurnDto:
    """Persist and return a terminal turn when a hard limit is reached.

    Writes step_type=stop, converged=False and marks the session abandoned.
    No LLM call is made.

    Args:
        session_id:     UUID of the target session.
        turn_id:        Pre-allocated turn UUID.
        turn_number:    1-based index for this turn.
        user_message:   Oracle's message that triggered the limit check.
        decision:       StateDecision from check_hard_limits.
        recommendation: Last show turn's recommendation, if any.

    Returns:
        A TurnDto with step_type=stop, converged=False.
    """
    reply = decision.reply or "Session limit reached. Thank you for using CinePal!"
    step_type = StepType.stop
    api_sessions.append_turn(
        session_id=session_id,
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=reply,
        step_type=step_type.value,
        converged=False,
        turn_id=turn_id,
    )
    api_sessions.mark_abandoned(session_id, decision.reason)
    log.warning(
        "turn terminated: hard limit",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "reason": decision.reason,
        },
    )
    now = datetime.now(timezone.utc)
    log.info(
        "turn handled",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "step_type": step_type.value,
            "converged": False,
        },
    )
    return TurnDto(
        turn_id=turn_id,
        session_id=session_id,
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=reply,
        step_type=step_type,
        converged=False,
        created_at=now,
        recommendation=recommendation,
    )


def natural_end_turn(
    *,
    session_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
    decision: StateDecision,
    preference_profile: UserProfile,
    recommendation: RecommendationDto | None = None,
) -> TurnDto:
    """Persist and return a natural-end turn detected by the LLM gate.

    Writes step_type=stop, converged=True, marks the session converged,
    and records an accept feedback row.

    Args:
        session_id:        UUID of the target session.
        turn_id:           Pre-allocated turn UUID.
        turn_number:       1-based index for this turn.
        user_message:      Oracle's message that the gate classified as natural end.
        decision:          StateDecision from the state agent.
        preference_profile: N-1 profile to persist with the converged session.
        recommendation:    Last show turn's recommendation, if any.

    Returns:
        A TurnDto with step_type=stop, converged=True.
    """
    reply = decision.reply or "Thank you — closing the session!"
    step_type = StepType.stop
    api_sessions.append_turn(
        session_id=session_id,
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=reply,
        step_type=step_type.value,
        converged=True,
        turn_id=turn_id,
    )
    api_sessions.write_feedback(
        session_id=session_id,
        turn_id=turn_id,
        feedback_level="global",
        feedback_type="accept",
        content=user_message,
        target_id=None,
    )
    api_sessions.mark_converged(session_id, preference_profile)
    log.info(
        "turn handled",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "step_type": step_type.value,
            "converged": True,
        },
    )
    now = datetime.now(timezone.utc)
    return TurnDto(
        turn_id=turn_id,
        session_id=session_id,
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=reply,
        step_type=step_type,
        converged=True,
        created_at=now,
        recommendation=recommendation,
    )


def emit_early_clarification(
    *,
    session_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
) -> TurnDto:
    """Persist and return a canned clarifying reply when retrieval yields no candidates.

    Args:
        session_id:   UUID of the target session.
        turn_id:      Pre-allocated turn UUID.
        turn_number:  1-based index for this turn.
        user_message: Oracle's message that produced empty retrieval.

    Returns:
        A TurnDto with step_type=ask and the canned reply.
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
    return TurnDto(
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
) -> TurnDto:
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
        A TurnDto with step_type=ask, converged=False.
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
    return TurnDto(
        turn_id=turn_id,
        session_id=session_id,
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=reply,
        step_type=step_type,
        converged=False,
        created_at=now,
    )


__all__ = [
    "emit_drift_clarification",
    "emit_early_clarification",
    "natural_end_turn",
    "terminate_turn",
]
