"""LLM convergence gate — detects natural session end and preference drift.

Makes one LLM call per turn using ``convergence_check_v2.j2``. The gate
operates on the N-1 preference profile (already persisted on the session row);
the Profile Agent runs AFTER this gate and updates the profile for the next turn.
"""

import json
import logging
from typing import Any
from uuid import UUID

from backend.api.types import SessionFull, StepType, TurnDetail
from backend.convergence.types import (
    ConvergenceAction,
    ConvergenceCheckResponse,
    ConvergenceDecision,
)
from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.settings import Settings, get_config_hash
from pathlib import Path

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent.parent / "prompts")


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


def check_llm_convergence(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
    preference_profile: dict[str, Any] | None,
    recent_turns: list[TurnDetail],
    show_count: int,
    cfg: Settings,
    accumulated_cost_usd: float = 0.0,
) -> ConvergenceDecision:
    """LLM gate: detects natural conversation end and preference drift in one call.

    Consumes the N-1 preference profile (from sessions.preference_profile) and the
    last 2 completed turns. The Profile Agent runs after this gate and updates the
    profile for the next turn.

    Args:
        session_id:         Target session UUID (for log correlation).
        run_id:             Experiment run UUID (for log correlation).
        turn_id:            Pre-allocated turn UUID (for log correlation).
        turn_number:        1-based index of the turn about to run.
        user_message:       Oracle's message for this turn.
        preference_profile: Structured profile dict from the previous turn, or
                            None if this is the first turn.
        recent_turns:       Up to 2 most recent completed turns (short history).
        show_count:         Number of show-type turns already completed.
        cfg:                Active typed settings (model, session limits).
        accumulated_cost_usd: Running USD cost for the current turn (cost guard).

    Returns:
        ``ConvergenceDecision`` with action one of:
          * ``proceed``       — normal pipeline should run.
          * ``natural_end``   — oracle wrapped up; mark converged.
          * ``clarify_drift`` — contradiction detected; emit clarification.

    Raises:
        LLMParseError:     If all retry attempts return malformed JSON.
        CostLimitExceeded: If the accumulated cost already exceeds the limit.
    """
    profile = preference_profile or {
        "constraints": [],
        "preferences": [],
        "attitudes": [],
        "summary": "",
    }

    text, prompt_hash = load_prompt(
        "convergence_check_v2",
        {
            "turn_number": turn_number,
            "max_turns": cfg.session.max_turns,
            "max_recommendations": cfg.session.max_recommendations,
            "recommendations_so_far": show_count,
            "preference_profile": profile,
            "recent_turns": [
                {
                    "user": t.user_message,
                    "assistant": t.assistant_message,
                    "step_type": t.step_type,
                }
                for t in recent_turns
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
            "n_recent_turns_in_ctx": len(recent_turns),
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
        step_type="convergence_check",
        messages=[{"role": "system", "content": text}],
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost_usd,
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
