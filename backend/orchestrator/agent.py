"""LLM-backed agent for the Orchestrator's recommendation-presentation step.

One public function: ``render_recommendation()``. It renders the system prompt
with the current cluster data and Decision Agent routing signal, assembles the
conversation history, calls ``llm_harness.call()``, parses the JSON response,
and returns a structured ``OrchestratorRecommendation``.

Convergence is NOT decided here — that is the Orchestrator's policy responsibility
(see ``_convergence_policy`` in orchestrator.py).  This step only produces the
user-facing reply text for a recommend-action turn.

Raises ``LLMParseError`` immediately on malformed JSON — no retry loop.
"""

import json
import logging
from pathlib import Path
from uuid import UUID

from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.settings import get_settings
from backend.models.clusters import ClusterSnapshot
from backend.models.decision import DecisionResult
from backend.models.llm import LLMParseError
from backend.models.orchestrator import OrchestratorRecommendation
from backend.models.retrieval import TurnDetail

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent / "prompts")


def render_recommendation(
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
        config_hash:          SHA-256 prefix of the session's YAML config snapshot.
        model_version:        LLM model string stored on the session row.
        max_turns:            Hard turn budget for this session.
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

    cluster_vars = [
        {
            "name": c.name,
            "description": c.description or "",
            "top_titles": [
                a.movie_id
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
        model_and_version=model_version,
        seed=cfg["model"]["seed"],
        max_tokens=cfg["model"]["max_tokens"],
        step_type="orchestrator_render",
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=float(cfg["session"]["cost_limit_usd"]),
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
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
        },
    )
    return OrchestratorRecommendation(reply=parsed["reply"])
