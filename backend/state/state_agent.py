"""State Agent — exposes both hard-limit and LLM drift/end/re-retrieve gates.

Splits the two gates into separate entry points so the orchestrator can run
them in the order that fits the async task graph:

* ``check_hard_limits`` is sync and pure-Python; the orchestrator calls it
  first, before spawning any LLM work, and short-circuits when it trips.
* ``check_gate`` is async and wraps the single LLM call; the orchestrator
  schedules it as one node in the per-turn task graph alongside profile
  extraction and (speculatively) retrieval or cluster refinement.

The gate consumes the N-1 preference profile (already on the session row);
the Profile Agent runs concurrently and updates the profile for the next turn.

No DB writes — the orchestrator owns all persistence.
"""

import logging
from typing import Any
from uuid import UUID

from backend.api.types import SessionRow, TurnRow, StepType
from backend.state.tools.hard_limits import check_hard_limits as _check_hard_limits
from backend.state.tools.llm_gate import check_llm_state
from backend.state.types import StateDecision
from backend.settings import Settings

log = logging.getLogger(__name__)

# Re-export so callers have a single ``state_agent`` surface.
check_hard_limits = _check_hard_limits


async def check_session_state(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
    full: SessionRow,
    preference_profile: dict[str, Any] | None,
    cfg: Settings,
    accumulated_cost_usd: float = 0.0,
    recommended_last_turn: list[str] | None = None,
    seen_films: list[str] | None = None,
) -> StateDecision:
    """LLM checker for the session state — detects natural end, 
    preference drift, and re-retrieve triggers.
    The orchestrator must call ``check_hard_limits`` first and short-circuit
    when that gate trips. ``check_session_state`` always issues an LLM call.
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
          * ``proceed``         — normal pipeline should run.
          * ``natural_end``     — oracle wrapped up; mark converged.
          * ``clarify_drift``   — contradiction detected; emit clarification.
          * ``drift_confirmed`` — oracle confirmed a preference change.
          * ``drift_dismissed`` — oracle explained away the contradiction.
          * ``re_retrieve``     — oracle signals all recommended films seen.

    Raises:
        LLMParseError:     If all LLM retry attempts return malformed JSON.
        CostLimitExceeded: If the session budget is exhausted.
    """
    show_count = sum(1 for t in full.turns if t.step_type == StepType.show.value)
    recent_turns: list[TurnRow] = full.turns[-2:]

    prev = full.turns[-1] if full.turns else None
    in_drift_clarification_state = prev is not None and any(
        f.turn_id == prev.id and f.feedback_type == "resolve_drift"
        for f in full.feedback
    )

    return await check_llm_state(
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
