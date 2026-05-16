"""Convergence policy — three-layer gate evaluated at the top of every turn.

The orchestrator consults these gates in order before running any agent:

  Layer 1: check_hard_limits        — pure Python, no LLM, no DB.
  Layer 2/3: check_llm_convergence  — single llm_harness call; detects natural
             conversation end AND preference drift in one round-trip.

Both functions return a ``ConvergenceDecision``. The orchestrator short-circuits
the normal pipeline whenever the action is not ``proceed``.
"""

import json
import logging
from typing import Any
from uuid import UUID

from backend.api.types import SessionFull, StepType
from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.orchestrator.types import (
    ConvergenceAction,
    ConvergenceCheckResponse,
    ConvergenceDecision,
)
from backend.settings import Settings, get_config_hash, prompts_dir

log = logging.getLogger(__name__)
_load_prompt = make_prompt_loader(prompts_dir("orchestrator"))


def _prompt_schema(model: type[ConvergenceCheckResponse]) -> dict:
    """Return an LLM-readable schema dict derived from *model*'s field definitions.

    Pydantic's model_json_schema() uses anyOf for nullable fields, which LLMs
    tend to mimic literally in their output. This helper flattens each field to
    {"type": "string | null"} so the representation matches what the LLM should
    produce, while the actual Pydantic validation remains the source of truth.
    """
    raw = model.model_json_schema()
    required = set(raw.get("required", []))
    properties: dict = {}
    for name, spec in raw.get("properties", {}).items():
        if "enum" in spec:
            properties[name] = {"type": "string", "enum": spec["enum"]}
        elif "anyOf" in spec:
            properties[name] = {"type": "string | null"}
        else:
            properties[name] = {"type": spec.get("type", "string")}
        if name in required:
            properties[name]["required"] = True
    return {"type": "object", "properties": properties}


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


def check_llm_convergence(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
    full: SessionFull,
    preference_profile: dict[str, Any],
    cfg: Settings,
) -> ConvergenceDecision:
    """LLM gate: detects natural conversation end and preference drift in one call.

    The gate renders ``convergence_check_v2.j2`` with conversation context and
    calls ``llm_harness.call`` exactly once, with ``response_schema`` set so the
    harness owns JSON parsing and Pydantic validation (including retries).

    Args:
        session_id:         Target session UUID (for log correlation).
        run_id:             Experiment run UUID (for log correlation).
        turn_id:            Pre-allocated turn UUID (for log correlation).
        turn_number:        1-based index of the turn about to run.
        user_message:       Oracle's message for this turn.
        full:               Full session state including prior turns.
        preference_profile: Rolling profile extracted from prior turns.
        cfg:                Active typed settings (model, session limits).

    Returns:
        ``ConvergenceDecision`` with action one of:
          * ``proceed``       — normal pipeline should run.
          * ``natural_end``   — oracle wrapped up; mark converged.
          * ``clarify_drift`` — contradiction detected; emit clarification.

    Raises:
        LLMParseError:     If all retry attempts return malformed JSON.
        CostLimitExceeded: If the accumulated cost already exceeds the limit.
    """
    show_count = sum(1 for t in full.turns if t.step_type == StepType.show.value)

    text, prompt_hash = _load_prompt(
        "convergence_check_v2",
        {
            "turn_number": turn_number,
            "max_turns": cfg.session.max_turns,
            "max_recommendations": cfg.session.max_recommendations,
            "recommendations_so_far": show_count,
            "preference_profile": preference_profile,
            "recent_turns": [
                {
                    "user": t.user_message,
                    "assistant": t.assistant_message,
                    "step_type": t.step_type,
                }
                for t in full.turns[-6:]
            ],
            "user_message": user_message,
            "response_schema_json": json.dumps(
                _prompt_schema(ConvergenceCheckResponse),
                indent=2,
            ),
        },
    )

    log.debug(
        "llm-gate dispatch",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "turn_number": turn_number,
            "prompt_hash": prompt_hash,
            "n_recent_turns_in_ctx": min(6, len(full.turns)),
        },
    )

    resp = llm_harness.call(
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        config_hash=get_config_hash(),
        model_and_version=cfg.model.name,
        provider=cfg.model.provider,
        seed=cfg.model.seed,
        max_tokens=cfg.model.max_tokens,
        step_type="orchestrator_convergence",
        messages=[{"role": "system", "content": text}],
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=0.0,
        response_schema=ConvergenceCheckResponse,
    )
    parsed: ConvergenceCheckResponse = resp.parsed  # type: ignore[assignment]

    log.info(
        "llm-gate convergence verdict",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "decision": parsed.decision,
            "reason": parsed.reason,
            "drift_topic": parsed.drift_topic,
        },
    )

    if parsed.decision == "natural_end":
        return ConvergenceDecision(
            action=ConvergenceAction.natural_end,
            reason=parsed.reason,
            reply=parsed.farewell_reply or "Thank you — closing the session!",
        )

    if parsed.decision == "clarify_drift":
        return ConvergenceDecision(
            action=ConvergenceAction.clarify_drift,
            reason=parsed.reason,
            reply=(
                parsed.clarify_reply
                or "I noticed a possible contradiction in your preferences — could you clarify?"
            ),
            drift_topic=parsed.drift_topic,
            prior_statement=parsed.prior_statement,
            current_statement=parsed.current_statement,
        )

    return ConvergenceDecision(
        action=ConvergenceAction.proceed,
        reason=parsed.reason,
    )
