"""Decision Agent — routes each turn to recommend or continue, and generates the
clarifying question when it chooses to continue.

Computes cluster entropy and relevance scores internally, then asks the LLM (via
llm_harness) to decide whether to surface a recommendation or ask a clarifying
question.  When the action is ``continue``, the question is included in the same
LLM response.  Returns a ``DecisionResult`` consumed by the Orchestrator.

No DB writes; all inputs are read-only.
"""

import logging
from pathlib import Path
from uuid import UUID

from typing import Any

from backend.decision.tools import entropy_calculator, relevance_scorer
from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.settings import get_config_hash, get_settings
from backend.api.types import ClusterSnapshot
from backend.decision.types import DecisionAction, DecisionQuestion, DecisionResponse, DecisionResult

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent / "prompts")

_MOVIES_PER_CLUSTER = 5


def decide(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_query: str,
    clusters: list[ClusterSnapshot],
    preference_profile: dict[str, Any] | None = None,
    accumulated_cost_usd: float = 0.0,
    prior_questions: list[str] | None = None,
) -> DecisionResult:
    """Return a routing decision for the current turn, including a clarifying question
    when the action is ``continue_``.

    When no clusters are available, short-circuits to ``continue_`` with entropy 1.0
    and no LLM call. No clarifying question is generated in that case.

    Args:
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        turn_number:          1-based turn index within the session.
        user_query:           Oracle's message for this turn.
        clusters:             Current cluster snapshots.
        preference_profile:   Structured oracle profile from the previous turn,
                              or None when no profile has been extracted yet.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).
        prior_questions:      Questions already asked in this session. Passed into
                              the prompt so the model avoids repeating them.

    Returns:
        A ``DecisionResult`` with routing action, best cluster id, rationale, entropy
        score, and — when action is ``continue_`` — the clarifying question fields.

    Raises:
        LLMParseError:       If the model returns non-JSON or a schema-invalid response.
        CostLimitExceeded:   If the session budget is exhausted.
        openai.APIError:     On a non-transient API error.
    """
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

    soft_scores = [[a.score for a in c.assignments] for c in clusters]
    entropy = entropy_calculator.compute(soft_scores)
    relevance = relevance_scorer.score(user_query, clusters)

    log.debug(
        "decision scores computed",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "entropy": entropy,
            "per_cluster": [
                {"id": str(c.id), "name": c.name, "relevance": relevance.get(c.id, 0.0), "size": len(c.assignments)}
                for c in clusters
            ],
        },
    )

    cfg = get_settings()
    config_hash = get_config_hash()
    model_and_version = cfg.model.name

    cluster_vars = [
        {
            "id": str(c.id),
            "name": c.name,
            "description": c.description or "",
            "relevance": relevance.get(c.id, 0.0),
            "movies": [
                a.title
                for a in sorted(c.assignments, key=lambda a: a.score, reverse=True)[:_MOVIES_PER_CLUSTER]
                if a.title
            ],
        }
        for c in clusters
    ]

    system_text, prompt_hash = load_prompt(
        "decision_v2",
        {
            "turn_number": turn_number,
            "max_turns": cfg.session.max_turns,
            "n_clusters": len(clusters),
            "user_query": user_query,
            "clusters": cluster_vars,
            "entropy_score": entropy,
            "preference_profile": preference_profile,
            "prior_questions": prior_questions or [],
        },
    )

    log.debug(
        "decision prompt built",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "prompt_hash": prompt_hash,
            "system_len": len(system_text),
            "n_clusters_in_prompt": len(cluster_vars),
        },
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_query},
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
        step_type="decision_route",
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost_usd,
        response_schema=DecisionResponse,
    )

    parsed: DecisionResponse = response.parsed  # type: ignore[assignment]

    log.debug(
        "decision raw LLM response",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "raw": response.content,
        },
    )

    action = (
        DecisionAction.recommend
        if parsed.action == "recommend"
        else DecisionAction.continue_
    )

    best_cluster_id: UUID | None = None
    if parsed.best_cluster_id:
        try:
            best_cluster_id = UUID(parsed.best_cluster_id)
        except ValueError:
            log.warning(
                "Decision agent: invalid best_cluster_id UUID, ignoring",
                extra={"raw": parsed.best_cluster_id, "session_id": str(session_id)},
            )

    log.debug(
        "Decision agent result",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "action": action.value,
            "question": parsed.question.text if parsed.question else None,
            "best_cluster_id": str(best_cluster_id) if best_cluster_id else None,
            "entropy_score": entropy,
        },
    )

    question: DecisionQuestion | None = parsed.question
    cluster_refs: list[UUID] = []
    if question is not None:
        for ref in question.cluster_refs:
            try:
                cluster_refs.append(UUID(ref))
            except ValueError:
                log.warning(
                    "Decision agent: invalid cluster_ref UUID in question, skipping",
                    extra={"raw": ref, "session_id": str(session_id)},
                )

    return DecisionResult(
        action=action,
        best_cluster_id=best_cluster_id,
        rationale=parsed.rationale,
        entropy_score=entropy,
        question_text=question.text if question else None,
        cluster_refs=cluster_refs,
    )
