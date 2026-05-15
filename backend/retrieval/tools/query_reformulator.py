"""query_reformulator — expand the oracle's query before vector retrieval.

Makes a single LLM call (step_type="retrieval_reformulate") that enriches the
oracle's raw utterance into a HyDE-style search string and extracts any films
the oracle wants to avoid.  Owned by the Retrieval System per architecture.md.

JSON parsing and Pydantic validation (with retry) are delegated to
``backend.llm.llm_harness``; this tool only renders the prompt, hands it to
the harness with the right schema, and surfaces the validated payload.
"""

import logging
from pathlib import Path
from uuid import UUID

from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.retrieval.types import ReformulatedQuery
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
) -> ReformulatedQuery:
    """Return a vibe-enriched search query plus any film exclusions extracted from *user_query*.

    On ``dry_run=True``, the canned fixture at
    ``tests/fixtures/dry_run/retrieval_reformulate.json`` is parsed by the
    harness and returned — the fixture's ``query`` and ``excluded_films`` are
    used as-is (no LLM call).

    Args:
        user_query:           Oracle's raw utterance for this turn.
        turn_number:          1-based turn index within the session.
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).
        dry_run:              If ``True``, skip the live LLM and use the fixture.

    Returns:
        ``ReformulatedQuery`` with the enriched query string and the list of
        film titles / series roots the oracle wants to avoid.

    Raises:
        LLMParseError:     If the model returns invalid JSON or fails schema
                           validation on every retry attempt.
        CostLimitExceeded: If the session budget is exhausted.
    """
    cfg = get_settings()
    config_hash = get_config_hash()
    model_and_version = cfg.model.name

    system_text, prompt_hash = load_prompt(
        "query_reformulate_v2",
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
        dry_run=dry_run,
        response_schema=ReformulatedQuery,
    )

    # response.parsed is guaranteed non-None when response_schema is set —
    # the harness either returns a validated model or raises LLMParseError.
    assert isinstance(response.parsed, ReformulatedQuery)
    result: ReformulatedQuery = response.parsed

    log.debug(
        "Query reformulation complete",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "query_len": len(result.query),
            "n_excluded": len(result.excluded_films),
        },
    )
    return result
