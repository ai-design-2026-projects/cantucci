"""Decision Agent — routes each turn to recommend or continue.

Computes cluster entropy and relevance scores, then asks the LLM (via
llm_harness) to decide whether to surface a recommendation or ask a
clarifying question.  Returns a ``DecisionResult`` consumed by the
Orchestrator.

No DB writes; all inputs are read-only.
"""

import json
import logging
from pathlib import Path
from uuid import UUID

from backend.decision.tools import entropy_calculator, relevance_scorer
from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.settings import get_config_hash, get_settings
from backend.api.types import ClusterSnapshot
from backend.decision.types import DecisionAction, DecisionResult
from backend.llm.types import LLMParseError

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent / "prompts")


def decide(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_query: str,
    clusters: list[ClusterSnapshot],
    accumulated_cost_usd: float = 0.0,
) -> DecisionResult:
    """Return a routing decision for the current turn.

    When no clusters are available (Cluster Agent placeholder), short-circuits
    to ``continue_`` with entropy 1.0 without making an LLM call.

    Args:
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        turn_number:          1-based turn index within the session.
        user_query:           Oracle's message for this turn.
        clusters:             Current cluster snapshots.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).

    Returns:
        A ``DecisionResult`` with routing action, best cluster id, rationale,
        and entropy score.

    Raises:
        LLMParseError:       If the model returns non-JSON or a mismatched shape.
        CostLimitExceeded:   If the session budget is exhausted.
        openai.APIError:     On a non-transient API error.
    """
    # Short-circuit when no clusters are available to avoid an LLM call and return a safe default
    if not clusters:
        log.warning(
            "Decision agent: no clusters available, routing to continue",
            extra={"session_id": str(session_id), "turn_number": turn_number},
        )
        return DecisionResult(
            action=DecisionAction.continue_,
            best_cluster_id=None,
            rationale="no clusters available — ask for clarification",
            entropy_score=1.0,
        )

    # Compute the entropy and relevance scores, then call the LLM to get the routing decision
    soft_scores = [[a.score for a in c.assignments] for c in clusters]
    entropy = entropy_calculator.compute(soft_scores)
    relevance = relevance_scorer.score(user_query, clusters)

    cfg = get_settings()
    config_hash = get_config_hash()
    model_and_version = cfg.model.name

    # For LLM logging and prompt construction, convert the clusters into dicts with the relevant fields and the relevance scores
    cluster_vars = [
        {
            "id": str(c.id),
            "name": c.name,
            "description": c.description or "",
            "relevance": relevance.get(c.id, 0.0),
        }
        for c in clusters
    ]

    # Construct the prompt and call the LLM harness to get the decision
    system_text, prompt_hash = load_prompt(
        "decision_v1",
        {
            "turn_number": turn_number,
            "max_turns": cfg.session.max_turns,
            "n_clusters": len(clusters),
            "user_query": user_query,
            "clusters": cluster_vars,
            "entropy_score": entropy,
        },
    )

    # For reproducibility, use the session RNG seed for the decision agent's LLM call (same as the describer and reformulator)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_query},
    ]

    # The decision agent is on the critical path for every turn, so we want to be especially careful with logging, cost guard, and error handling in the LLM call it makes.
    response = llm_harness.call(
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        config_hash=config_hash,
        model_and_version=model_and_version,
        provider=cfg.model.provider,
        seed=cfg.model.seed,
        max_tokens=cfg.model.max_tokens,
        step_type="decision_route",
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost_usd,
    )

    # Parse the response and validate the shape
    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        raise LLMParseError(step_type="decision_route", raw=response.content)
    # The expected fields are "action" (either "recommend" or "continue"), "rationale" (string), and "entropy_score" (number).  
    if (
        parsed.get("action") not in {"recommend", "continue"}
        or "rationale" not in parsed
        or "entropy_score" not in parsed
    ):
        raise LLMParseError(step_type="decision_route", raw=response.content)

    # The LLM can optionally return a "best_cluster_id" field with the UUID of the cluster it thinks is best to recommend; if it's missing or invalid, we log a warning and proceed with None
    raw_cluster_id = parsed.get("best_cluster_id")
    best_cluster_id: UUID | None = None
    if raw_cluster_id:
        try:
            best_cluster_id = UUID(raw_cluster_id)
        except ValueError:
            log.warning(
                "Decision agent: invalid best_cluster_id UUID, ignoring",
                extra={"raw": raw_cluster_id, "session_id": str(session_id)},
            )

    # Convert the action field to a DecisionAction enum
    action = (
        DecisionAction.recommend
        if parsed["action"] == "recommend"
        else DecisionAction.continue_
    )

    # Log the decision result with the entropy score for monitoring and analysis
    log.debug(
        "Decision agent result",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "action": action.value,
            "entropy_score": parsed["entropy_score"],
        },
    )
    # Return the decision result to the orchestrator for routing
    return DecisionResult(
        action=action,
        best_cluster_id=best_cluster_id,
        rationale=parsed["rationale"],
        entropy_score=float(parsed["entropy_score"]),
    )
