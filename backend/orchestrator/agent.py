"""LLM-backed recommendation agent for the Orchestrator.

One public function: ``respond()``. It loads config, renders the system prompt,
assembles the conversation history, and calls ``llm_harness.call()``.

All LLM calls go through ``backend.llm.llm_harness`` — never instantiate a
model client directly here.
"""

import logging
from pathlib import Path
from uuid import UUID

from backend.llm import llm_harness
from backend.llm.configs import load_config
from backend.llm.prompts import make_prompt_loader
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
) -> str:
    """Make one LLM call and return the assistant's reply.

    Loads the default config for cost/token parameters. Uses the session's
    ``model_version`` and ``config_hash`` for logging so the call is
    replayable from the session log.

    Args:
        session_id:    UUID of the current session (for harness logging).
        run_id:        UUID of the parent run (for harness logging).
        turn_id:       Pre-allocated UUID of the turn (for log correlation).
        turn_number:   1-based turn index within the session.
        user_message:  Oracle's message for this turn.
        history:       All prior turns in ascending turn_number order.
        persona_id:    Oracle persona identifier, or None for human oracles.
        config_hash:   SHA-256 prefix of the session's YAML config snapshot.
        model_version: LLM model string stored on the session row.

    Returns:
        The assistant's reply text.

    Raises:
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
            "max_turns": cfg["session"]["max_turns"],
            "turn_number": turn_number,
            "persona_id": persona_id or "unknown",
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
        step_type="show",
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=float(cfg["session"]["cost_limit_usd"]),
        accumulated_cost_usd=0.0,
    )

    log.debug(
        "agent responded",
        extra={"session_id": str(session_id), "turn_number": turn_number},
    )
    return response.content
