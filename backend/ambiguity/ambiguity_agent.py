"""Ambiguity Agent — generates a focused clarifying question.

Activated when the Decision Agent chooses ``continue``.  Identifies the
sharpest divergence between the top 2–3 clusters and returns a single
binary or forced-choice question for the oracle.

No DB writes; all inputs are read-only.
"""

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.settings import get_config_hash, get_settings
from backend.ambiguity.types import AmbiguityQuestion
from backend.api.types import ClusterSnapshot
from backend.llm.types import LLMParseError

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent / "prompts")

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
    preference_profile: dict[str, Any] | None = None,
    accumulated_cost_usd: float = 0.0,
) -> AmbiguityQuestion:
    """Generate a clarifying question targeting the sharpest cluster divergence.

    Args:
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        turn_number:          1-based turn index within the session.
        user_query:           Oracle's message for this turn.
        clusters:             Current cluster snapshots (top 2–3 are used).
        entropy_score:        Pre-computed entropy from the Decision Agent.
        prior_questions:      Assistant messages from previous ask-type turns,
                              used to avoid repeating questions.
        preference_profile:   Structured oracle profile from the previous turn,
                              or None when no profile has been extracted yet.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).

    Returns:
        An ``AmbiguityQuestion`` with the question text, UI format hint, and
        the cluster IDs the question targets.

    Raises:
        LLMParseError:       If the model returns non-JSON or a mismatched shape.
        CostLimitExceeded:   If the session budget is exhausted.
        openai.APIError:     On a non-transient API error.
    """
    cfg = get_settings()
    config_hash = get_config_hash()
    model_and_version = cfg.model.name
    top_clusters = clusters[:cfg.ambiguity.max_cluster_context]

    log.debug(
        "ambiguity top clusters selected",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "n_total_clusters": len(clusters),
            "n_top_clusters": len(top_clusters),
            "cluster_names": [c.name for c in top_clusters],
            "entropy_score": entropy_score,
            "n_prior_questions": len(prior_questions),
        },
    )

    # Prepare cluster context for the prompt, including ID, name, and description.
    cluster_vars = [
        {"id": str(c.id), "name": c.name, "description": c.description or ""}
        for c in top_clusters
    ]

    # Load the prompt template and fill in the variables, including the user query,
    system_text, prompt_hash = load_prompt(
        "ambiguity_v2",
        {
            "turn_number": turn_number,
            "max_turns": cfg.session.max_turns,
            "user_query": user_query,
            "clusters": cluster_vars,
            "entropy_score": entropy_score,
            "prior_questions": prior_questions,
            "preference_profile": preference_profile,
        },
    )

    # Construct the messages for the LLM call
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_query},
    ]

    # Call the LLM harness to generate the question, passing all relevant metadata for logging and cost tracking
    response = llm_harness.call(
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        config_hash=config_hash,
        model_and_version=model_and_version,
        provider=cfg.model.provider,
        seed=cfg.model.seed,
        max_tokens=cfg.model.max_tokens,
        step_type="ambiguity_question",
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost_usd,
    )
    log.debug(
        "ambiguity raw LLM response",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "raw": response.content,
        },
    )

    # Parse the LLM response, expecting a JSON object with 'question_text', 'ui_format', and 'cluster_refs' fields. Validate the types and handle any parsing errors.
    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        raise LLMParseError(step_type="ambiguity_question", raw=response.content)

    # Validate the presence and types of the expected fields in the parsed response
    if (
        not isinstance(parsed.get("question_text"), str)
        or not isinstance(parsed.get("ui_format"), str)
        or not isinstance(parsed.get("cluster_refs"), list)
    ):
        raise LLMParseError(step_type="ambiguity_question", raw=response.content)

    # Convert the cluster_refs from strings to UUIDs, handling any invalid UUIDs gracefully by logging a warning and skipping them.
    cluster_refs: list[UUID] = []
    for raw_id in parsed["cluster_refs"]:
        try:
            cluster_refs.append(UUID(raw_id))
        except (ValueError, TypeError):
            log.warning(
                "ambiguity agent: invalid cluster_ref UUID, skipping",
                extra={"raw": raw_id, "session_id": str(session_id)},
            )

    # Log the generated question and its UI format for monitoring and debugging purposes
    log.debug(
        "ambiguity agent generated question",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "ui_format": parsed["ui_format"],
            "question_text": parsed["question_text"],
            "n_cluster_refs": len(cluster_refs),
        },
    )
    return AmbiguityQuestion(
        question_text=parsed["question_text"],
        ui_format=parsed["ui_format"],
        cluster_refs=cluster_refs,
    )
