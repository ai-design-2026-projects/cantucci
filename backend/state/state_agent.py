"""State Agent — evaluates both hard limits and LLM drift/end/re-retrieve gate.

Splits out of the orchestrator so state logic has its own module,
prompt, types, and test surface. The orchestrator calls ``check()`` at the
top of every turn, before retrieval or clustering, and short-circuits when
the action is not ``proceed``.

The gate consumes the N-1 preference profile (already on the session row);
the Profile Agent runs AFTER the turn pipeline and updates the profile for
the next turn.

No DB writes — the orchestrator owns all persistence.
"""

import logging
from typing import Any
from uuid import UUID

from backend.api.types import SessionFull, StepType, TurnDetail
from backend.state.tools.hard_limits import check_hard_limits
from backend.state.tools.llm_gate import check_llm_state
from backend.state.types import StateAction, StateDecision
from backend.settings import Settings

log = logging.getLogger(__name__)


def check(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
    full: SessionFull,
    preference_profile: dict[str, Any] | None,
    cfg: Settings,
    accumulated_cost_usd: float = 0.0,
    recommended_last_turn: list[str] | None = None,
    seen_films: list[str] | None = None,
) -> StateDecision:
    """Evaluate all state gates for the current turn.

    Runs in two layers:
      1. Hard-limit gate (pure Python, no LLM): terminates the session when
         max_turns or max_recommendations is exceeded.
      2. LLM gate: detects natural conversation end, preference drift, and
         re-retrieve triggers.

    The LLM gate is skipped when the hard-limit gate trips.

    Args:
        session_id:           UUID of the target session.
        run_id:               UUID of the parent run.
        turn_id:              Pre-allocated turn UUID (for log correlation).
        turn_number:          1-based index of the turn about to run.
        user_message:         Oracle's message for this turn.
        full:                 Full session state including prior turns.
        preference_profile:   Structured profile dict from the previous turn,
                              or None on the first turn.
        cfg:                  Active typed settings (model, session limits).
        accumulated_cost_usd: Running USD cost for the current turn (cost guard).
        recommended_last_turn: Titles shown in the most recent recommendation turn.
        seen_films:           Accumulated seen-film titles across the session.

    Returns:
        ``StateDecision`` with action one of:
          * ``proceed``       — normal pipeline should run.
          * ``terminate``     — hard limit hit; write stop turn, mark abandoned.
          * ``natural_end``   — oracle wrapped up; mark converged.
          * ``clarify_drift`` — contradiction detected; emit clarification.
          * ``re_retrieve``   — oracle signals all recommended films already seen.

    Raises:
        LLMParseError:     If all LLM retry attempts return malformed JSON.
        CostLimitExceeded: If the session budget is exhausted.
    """
    hard = check_hard_limits(turn_number=turn_number, full=full, cfg=cfg)
    if hard.action is StateAction.terminate:
        return hard

    show_count = sum(1 for t in full.turns if t.step_type == StepType.show.value)
    recent_turns: list[TurnDetail] = full.turns[-2:]

    prev = full.turns[-1] if full.turns else None
    in_drift_clarification_state = prev is not None and any(
        f.turn_id == prev.id and f.feedback_type == "resolve_drift"
        for f in full.feedback
    )

    return check_llm_state(
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        turn_number=turn_number,
        user_message=user_message,
        preference_profile=preference_profile,
        recent_turns=recent_turns,
        show_count=show_count,
        cfg=cfg,
        accumulated_cost_usd=accumulated_cost_usd,
        in_drift_clarification_state=in_drift_clarification_state,
        recommended_last_turn=recommended_last_turn,
        seen_films=seen_films,
    )
