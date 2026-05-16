"""Deterministic hard-limit convergence gate — no LLM, no DB.

Trips when the turn budget or recommendation cap has been exhausted.
"""

import logging

from backend.api.types import SessionFull, StepType
from backend.convergence.types import ConvergenceAction, ConvergenceDecision
from backend.settings import Settings

log = logging.getLogger(__name__)


def check_hard_limits(
    *,
    turn_number: int,
    full: SessionFull,
    cfg: Settings,
) -> ConvergenceDecision:
    """Deterministic hard-limit gate. Runs BEFORE any LLM call.

    Trips when either:
      * turn_number > cfg.session.max_turns  — turn budget exhausted.
      * count(step_type=show in history) >= cfg.session.max_recommendations
        — recommendation cap reached.

    Args:
        turn_number: 1-based index of the turn about to run.
        full:        Full session state including prior turn history.
        cfg:         Active typed settings (max_turns, max_recommendations).

    Returns:
        ``ConvergenceDecision(action=proceed)`` when neither limit is hit;
        ``ConvergenceDecision(action=terminate, reply=<canned msg>)`` otherwise.
    """
    max_turns = cfg.session.max_turns
    max_recs = cfg.session.max_recommendations
    show_count = sum(1 for t in full.turns if t.step_type == StepType.show.value)

    log.debug(
        "hard-limit check",
        extra={
            "session_id": str(full.session_id),
            "turn_number": turn_number,
            "max_turns": max_turns,
            "max_recommendations": max_recs,
            "show_count": show_count,
        },
    )

    if turn_number > max_turns:
        log.warning(
            "hard limit: max_turns exceeded",
            extra={
                "session_id": str(full.session_id),
                "turn_number": turn_number,
                "max_turns": max_turns,
            },
        )
        return ConvergenceDecision(
            action=ConvergenceAction.terminate,
            reason=f"turn_number {turn_number} > max_turns {max_turns}",
            reply=(
                f"We've reached the maximum of {max_turns} turns for this session. "
                "Thank you for exploring with CinePal!"
            ),
        )

    if show_count >= max_recs:
        log.warning(
            "hard limit: max_recommendations reached",
            extra={
                "session_id": str(full.session_id),
                "show_count": show_count,
                "max_recommendations": max_recs,
            },
        )
        return ConvergenceDecision(
            action=ConvergenceAction.terminate,
            reason=f"show_count {show_count} >= max_recommendations {max_recs}",
            reply=(
                f"We've presented {show_count} recommendation sets — "
                "the maximum for this session. Thank you for exploring with CinePal!"
            ),
        )

    return ConvergenceDecision(
        action=ConvergenceAction.proceed,
        reason="under all hard limits",
    )
