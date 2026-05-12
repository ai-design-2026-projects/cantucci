"""LLM-backed agent for the Orchestrator.

One public function: ``respond()``. It renders the system prompt (including
the Decision Agent routing signal and convergence context), assembles the
conversation history, calls ``llm_harness.call()``, parses the JSON response,
and returns a structured ``OrchestratorTurnResponse``.

Raises ``LLMParseError`` immediately on malformed JSON — no retry loop.
"""

import json
import logging
from pathlib import Path
from uuid import UUID

from backend.llm import llm_harness
from backend.llm.configs import load_config
from backend.llm.prompts import make_prompt_loader
from backend.models.decision import DecisionResult
from backend.models.llm import LLMParseError
from backend.models.orchestrator import OrchestratorTurnResponse
from backend.models.retrieval import TurnDetail

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent / "prompts")


def respond(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
    history: list[TurnDetail],
    persona_id: str | None,
    config_hash: str,
    model_version: str,
    max_turns: int,
    decision: DecisionResult,
) -> OrchestratorTurnResponse:
    """Make one LLM call and return the parsed structured response.

    Args:
        session_id:    UUID of the current session.
        run_id:        UUID of the parent run.
        turn_id:       Pre-allocated UUID of the turn (for log correlation).
        turn_number:   1-based turn index within the session.
        user_message:  Oracle's message for this turn.
        history:       All prior turns in ascending turn_number order.
        persona_id:    Oracle persona identifier, or None for human oracles.
        config_hash:   SHA-256 prefix of the session's YAML config snapshot.
        model_version: LLM model string stored on the session row.
        max_turns:     Hard turn budget for this session.
        decision:      Routing signal from the Decision Agent for this turn.

    Returns:
        A parsed ``OrchestratorTurnResponse`` with ``reply``, ``converged``,
        and ``preference_profile``.

    Raises:
        LLMParseError:           If the model returns non-JSON or a JSON object
                                 that does not match the expected shape, or if
                                 ``converged=True`` without a ``preference_profile``.
        FileNotFoundError:       If the prompt template is missing.
        CostLimitExceeded:       If the session budget is exhausted.
        openai.APIError:         On a non-transient API error.
        openai.RateLimitError /
        APITimeoutError /
        APIConnectionError:      After 3 failed retry attempts.
    """
    cfg, _ = load_config("default")

    system_text, prompt_hash = load_prompt(
        "orchestrator_system_v1",
        {
            "max_turns": max_turns,
            "turn_number": turn_number,
            "persona_id": persona_id or "unknown",
            "decision_action": decision.action.value,
            "decision_rationale": decision.rationale,
            "convergence_turns": cfg["session"]["convergence_turns"],
        },
    )

    history_messages: list[dict[str, str]] = []
    for turn in history:
        history_messages.append({"role": "user", "content": turn.user_message})
        if turn.assistant_message:
            history_messages.append({"role": "assistant", "content": turn.assistant_message})

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_text},
        *history_messages,
        {"role": "user", "content": user_message},
    ]

    response = llm_harness.call(
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        config_hash=config_hash,
        model_and_version=model_version,
        seed=cfg["model"]["seed"],
        max_tokens=cfg["model"]["max_tokens"],
        step_type="orchestrator_turn",
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=float(cfg["session"]["cost_limit_usd"]),
        accumulated_cost_usd=0.0,
    )

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        raise LLMParseError(step_type="orchestrator_turn", raw=response.content)

    if (
        not isinstance(parsed.get("reply"), str)
        or not isinstance(parsed.get("converged"), bool)
        or "preference_profile" not in parsed
    ):
        raise LLMParseError(step_type="orchestrator_turn", raw=response.content)

    if parsed["converged"] and parsed["preference_profile"] is None:
        raise LLMParseError(step_type="orchestrator_turn", raw=response.content)

    log.debug(
        "agent responded",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "converged": parsed["converged"],
        },
    )
    return OrchestratorTurnResponse(
        reply=parsed["reply"],
        converged=parsed["converged"],
        preference_profile=parsed["preference_profile"],
    )
