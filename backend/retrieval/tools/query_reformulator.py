"""query_reformulator — expand the oracle's query before vector retrieval.

Two entry points cover the two retrieval modes:

- ``from_message`` — reads the oracle's raw utterance and produces a HyDE-style
  search string plus a list of film titles to exclude. Used on first-turn and
  ``proceed`` actions where we want the LLM to interpret the oracle's words.
  (step_type="retrieval_reformulate")

- ``from_profile`` — reads the extracted preference-profile summary and
  produces only a HyDE-style search string. Exclusions are passed deterministically
  by the caller (the orchestrator's ``seen_films`` list) and must NOT be extracted
  by the LLM. Used on ``drift_confirmed`` and ``re_retrieve`` actions.
  (step_type="retrieval_reformulate_profile")

JSON parsing and Pydantic validation (with retry) are delegated to
``backend.llm.llm_harness``; this tool only renders the prompt, hands it to
the harness with the right schema, and surfaces the validated payload.
"""

import logging
from pathlib import Path
from uuid import UUID

from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.retrieval.types import ReformulatedProfileQuery, ReformulatedQuery
from backend.settings import get_config_hash, get_settings

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent.parent / "prompts")

_STEP_TYPE_MESSAGE = "retrieval_reformulate"
_STEP_TYPE_PROFILE = "retrieval_reformulate_profile"


async def from_message(
    *,
    user_query: str,
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
    model_and_version = cfg.models.fast.name

    log.debug(
        "query reformulator input",
        extra={"session_id": str(session_id), "turn_id": str(turn_id), "user_query": user_query},
    )

    system_text, prompt_hash = load_prompt(
        "query_reformulate_v2",
        {
            "user_query": user_query,
        },
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_query},
    ]

    response = await llm_harness.call(
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        config_hash=config_hash,
        model_and_version=model_and_version,
        provider=cfg.models.fast.provider,
        seed=cfg.models.fast.seed,
        max_tokens=cfg.models.fast.max_tokens,
        step_type=_STEP_TYPE_MESSAGE,
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
    return response.parsed


async def from_profile(
    *,
    summary: str,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> ReformulatedProfileQuery:
    """Return a HyDE-style search query derived from the preference-profile *summary*.

    Unlike ``from_message``, this function does NOT extract excluded films — the
    caller (orchestrator) owns that list and passes it directly to vector search.
    This guarantees that films in ``seen_films`` are always excluded, regardless
    of how the LLM paraphrases the summary.

    On ``dry_run=True``, the canned fixture at
    ``tests/fixtures/dry_run/retrieval_reformulate_profile.json`` is used.

    Args:
        summary:              Preference-profile summary text from the profile agent.
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).
        dry_run:              If ``True``, skip the live LLM and use the fixture.

    Returns:
        ``ReformulatedProfileQuery`` with the enriched query string only.

    Raises:
        LLMParseError:     If the model returns invalid JSON or fails schema
                           validation on every retry attempt.
        CostLimitExceeded: If the session budget is exhausted.
    """
    cfg = get_settings()
    config_hash = get_config_hash()
    model_and_version = cfg.models.fast.name

    log.debug(
        "profile reformulator input",
        extra={"session_id": str(session_id), "turn_id": str(turn_id), "summary_len": len(summary)},
    )

    system_text, prompt_hash = load_prompt(
        "query_reformulate_profile_v2",
        {
            "summary": summary,
        },
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": "Generate the search query for this profile summary."},
    ]

    response = await llm_harness.call(
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        config_hash=config_hash,
        model_and_version=model_and_version,
        provider=cfg.models.fast.provider,
        seed=cfg.models.fast.seed,
        max_tokens=cfg.models.fast.max_tokens,
        step_type=_STEP_TYPE_PROFILE,
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost_usd,
        dry_run=dry_run,
        response_schema=ReformulatedProfileQuery,
    )

    assert isinstance(response.parsed, ReformulatedProfileQuery)
    return response.parsed
