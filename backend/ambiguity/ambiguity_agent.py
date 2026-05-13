"""Ambiguity Agent — generates a focused clarifying question.

Activated when the Decision Agent chooses ``continue``.  Identifies the
sharpest divergence between the top 2–3 clusters and returns a single
binary or forced-choice question for the oracle.

No DB writes; all inputs are read-only.
"""

import json
import logging
from pathlib import Path
from uuid import UUID

from backend.llm import llm_harness
from backend.llm.configs import load_config
from backend.llm.prompts import make_prompt_loader
from backend.models.ambiguity import AmbiguityQuestion
from backend.models.clusters import ClusterSnapshot
from backend.models.llm import LLMParseError

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent / "prompts")

_MAX_CLUSTER_CONTEXT = 3


def generate_question(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_query: str,
    clusters: list[ClusterSnapshot],
    entropy_score: float,
    prior_questions: list[str],
    config_hash: str,
    model_version: str,
) -> AmbiguityQuestion:
    """Generate a clarifying question targeting the sharpest cluster divergence.

    Args:
        session_id:      UUID of the current session.
        run_id:          UUID of the parent run.
        turn_id:         UUID of the current turn.
        turn_number:     1-based turn index within the session.
        user_query:      Oracle's message for this turn.
        clusters:        Current cluster snapshots (top 2–3 are used).
        entropy_score:   Pre-computed entropy from the Decision Agent.
        prior_questions: Assistant messages from previous ask-type turns,
                         used to avoid repeating questions.
        config_hash:     SHA-256 prefix of the session's YAML config snapshot.
        model_version:   LLM model string stored on the session row.

    Returns:
        An ``AmbiguityQuestion`` with the question text, UI format hint, and
        the cluster IDs the question targets.

    Raises:
        LLMParseError:       If the model returns non-JSON or a mismatched shape.
        CostLimitExceeded:   If the session budget is exhausted.
        openai.APIError:     On a non-transient API error.
    """
    top_clusters = clusters[:_MAX_CLUSTER_CONTEXT]

    cluster_vars = [
        {"id": str(c.id), "name": c.name, "description": c.description or ""}
        for c in top_clusters
    ]

    cfg, _ = load_config("default")

    system_text, prompt_hash = load_prompt(
        "ambiguity_v1",
        {
            "turn_number": turn_number,
            "max_turns": cfg["session"]["max_turns"],
            "user_query": user_query,
            "clusters": cluster_vars,
            "entropy_score": entropy_score,
            "prior_questions": prior_questions,
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
        model_and_version=model_version,
        seed=cfg["model"]["seed"],
        max_tokens=cfg["model"]["max_tokens"],
        step_type="ambiguity_question",
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=float(cfg["session"]["cost_limit_usd"]),
        accumulated_cost_usd=0.0,
    )

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        raise LLMParseError(step_type="ambiguity_question", raw=response.content)

    if (
        not isinstance(parsed.get("question_text"), str)
        or not isinstance(parsed.get("ui_format"), str)
        or not isinstance(parsed.get("cluster_refs"), list)
    ):
        raise LLMParseError(step_type="ambiguity_question", raw=response.content)

    cluster_refs: list[UUID] = []
    for raw_id in parsed["cluster_refs"]:
        try:
            cluster_refs.append(UUID(raw_id))
        except (ValueError, TypeError):
            log.warning(
                "ambiguity agent: invalid cluster_ref UUID, skipping",
                extra={"raw": raw_id, "session_id": str(session_id)},
            )

    log.debug(
        "ambiguity agent generated question",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "ui_format": parsed["ui_format"],
        },
    )
    return AmbiguityQuestion(
        question_text=parsed["question_text"],
        ui_format=parsed["ui_format"],
        cluster_refs=cluster_refs,
    )
