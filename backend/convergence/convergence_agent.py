"""Convergence Agent — evaluates both hard limits and LLM drift/end gate.

Splits out of the orchestrator so convergence logic has its own module,
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
from backend.convergence.tools.hard_limits import check_hard_limits
from backend.convergence.tools.llm_gate import check_llm_convergence
from backend.convergence.types import ConvergenceAction, ConvergenceDecision
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
) -> ConvergenceDecision:
    """Evaluate all convergence gates for the current turn.

    Runs in two layers:
      1. Hard-limit gate (pure Python, no LLM): terminates the session when
         max_turns or max_recommendations is exceeded.
      2. LLM gate: detects natural conversation end and preference drift.

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

    Returns:
        ``ConvergenceDecision`` with action one of:
          * ``proceed``       — normal pipeline should run.
          * ``terminate``     — hard limit hit; write stop turn, mark abandoned.
          * ``natural_end``   — oracle wrapped up; mark converged.
          * ``clarify_drift`` — contradiction detected; emit clarification.

    Raises:
        LLMParseError:     If all LLM retry attempts return malformed JSON.
        CostLimitExceeded: If the session budget is exhausted.
    """
    hard = check_hard_limits(turn_number=turn_number, full=full, cfg=cfg)
    if hard.action is ConvergenceAction.terminate:
        return hard

    show_count = sum(1 for t in full.turns if t.step_type == StepType.show.value)
    recent_turns: list[TurnDetail] = full.turns[-2:]

    return check_llm_convergence(
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
    )
