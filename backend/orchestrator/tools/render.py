"""Recommendation rendering tool for the Orchestrator's presentation step.

One public function: ``render_recommendation()``. It renders the system prompt
with the current cluster data and Decision Agent routing signal, assembles the
conversation history, calls ``llm_harness.call()``, parses the JSON response,
and returns a structured ``OrchestratorRecommendation``.

Convergence is NOT decided here — that is the Orchestrator's policy responsibility
(see ``convergence_policy`` in tools/policy.py). This step only produces the
user-facing reply text for a recommend-action turn.

Raises ``LLMParseError`` immediately on malformed JSON — no retry loop.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.api.types import ClusterSnapshot, TurnDetail
from backend.decision.types import DecisionResult
from backend.llm.types import LLMParseError
from backend.settings import get_config_hash, get_settings

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent.parent / "prompts")


@dataclass
class OrchestratorRecommendation:
    """Structured output parsed from the render step.

    The orchestrator's prompt instructs the model to return valid JSON
    matching this shape. ``render_recommendation()`` parses and validates
    the raw string; any mismatch raises ``LLMParseError``.

    Convergence is determined by the Orchestrator's policy (not the LLM).

    Attributes:
        reply: User-facing message presenting the current clusters and
               inviting oracle feedback.
    """

    reply: str


def render_recommendation(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
    history: list[TurnDetail],
    persona_id: str | None,
    decision: DecisionResult,
    clusters: list[ClusterSnapshot],
    accumulated_cost_usd: float = 0.0,
) -> OrchestratorRecommendation:
    """Make one LLM call to produce the oracle-facing recommendation reply.

    Args:
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              Pre-allocated UUID of the turn (for log correlation).
        turn_number:          1-based turn index within the session.
        user_message:         Oracle's message for this turn.
        history:              All prior turns in ascending turn_number order.
        persona_id:           Oracle persona identifier, or None for human oracles.
        decision:             Routing signal from the Decision Agent for this turn.
        clusters:             Current cluster snapshots to present.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).

    Returns:
        A parsed ``OrchestratorRecommendation`` with the oracle-facing ``reply``.

    Raises:
        LLMParseError:     If the model returns non-JSON or a JSON object that
                           does not contain a string ``reply`` field.
        FileNotFoundError: If the prompt template is missing.
        CostLimitExceeded: If the session budget is exhausted.
        openai.APIError:   On a non-transient API error.
    """
    cfg = get_settings()
    config_hash = get_config_hash()
    model_and_version = cfg.model.name
    max_turns = cfg.session.max_turns

    cluster_vars = [
        {
            "name": c.name,
            "description": c.description or "",
            "top_titles": [
                a.title or str(a.movie_id)
                for a in sorted(c.assignments, key=lambda x: x.score, reverse=True)
                if not a.excluded
            ][:5],
        }
        for c in clusters
    ]

    system_text, prompt_hash = load_prompt(
        "orchestrator_system_v1",
        {
            "max_turns": max_turns,
            "turn_number": turn_number,
            "persona_id": persona_id or "unknown",
            "decision_action": decision.action.value,
            "decision_rationale": decision.rationale,
            "convergence_turns": cfg.session.convergence_turns,
            "clusters": cluster_vars,
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
        model_and_version=model_and_version,
        provider=cfg.model.provider,
        seed=cfg.model.seed,
        max_tokens=cfg.model.max_tokens,
        step_type="orchestrator_render",
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=float(cfg.session.cost_limit_usd),
        accumulated_cost_usd=accumulated_cost_usd,
    )

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        raise LLMParseError(step_type="orchestrator_render", raw=response.content)

    if not isinstance(parsed.get("reply"), str):
        raise LLMParseError(step_type="orchestrator_render", raw=response.content)

    log.debug(
        "orchestrator render complete",
        extra={"session_id": str(session_id), "turn_number": turn_number},
    )
    return OrchestratorRecommendation(reply=parsed["reply"])
