"""query_reformulator — expand the oracle's query before vector retrieval.

Makes a single LLM call (step_type="retrieval_reformulate") to enrich the
oracle's raw utterance with themes, tone, era, and aesthetic cues that improve
vector-search recall.  Owned by the Retrieval System per architecture.md.
"""

import json
import logging
from pathlib import Path
from uuid import UUID

from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.llm.types import LLMParseError
from backend.settings import get_config_hash, get_settings

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent.parent / "prompts")

_STEP_TYPE = "retrieval_reformulate"


def reformulate(
    *,
    user_query: str,
    turn_number: int,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> str:
    """Return a vibe-enriched search query derived from *user_query*.

    On ``dry_run=True``, the raw *user_query* is returned unchanged (the LLM
    call is skipped and the canned ``[DRY RUN]`` content would fail JSON parsing).

    Args:
        user_query:           Oracle's raw utterance for this turn.
        turn_number:          1-based turn index within the session.
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).
        dry_run:              If ``True``, skip the LLM call and return *user_query*.

    Returns:
        Reformulated query string enriched with cinematic themes and aesthetics.

    Raises:
        LLMParseError:     If the model returns non-JSON or a missing field.
        CostLimitExceeded: If the session budget is exhausted.
    """
    if dry_run:
        log.debug(
            "query_reformulator dry_run: returning raw query",
            extra={"session_id": str(session_id)},
        )
        return user_query

    cfg = get_settings()
    config_hash = get_config_hash()
    model_and_version = cfg.model.name

    system_text, prompt_hash = load_prompt(
        "query_reformulate_v1",
        {
            "user_query": user_query,
            "turn_number": turn_number,
            "max_turns": cfg.session.max_turns,
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
        step_type=_STEP_TYPE,
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost_usd,
    )

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)

    if not isinstance(parsed.get("reformulated_query"), str):
        raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)

    reformulated: str = parsed["reformulated_query"].strip()
    if not reformulated:
        raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)

    log.debug(
        "Query reformulation complete",
        extra={"session_id": str(session_id), "turn_number": turn_number, "query_len": len(reformulated)},
    )
    return reformulated
