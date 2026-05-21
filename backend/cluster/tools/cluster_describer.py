"""cluster_describer — assign a name and description to each cluster via LLM.

A single batched call sends all clusters' top titles, genres, and overviews to
the model, which returns a JSON object whose ``clusters`` field has one
``{cluster_index, name, description}`` per HDBSCAN cluster.  One call per turn
is cheaper and lets the model differentiate cluster names by contrast.

JSON parsing and Pydantic validation (with retry) are delegated to
``backend.llm.llm_harness``; this tool only renders the prompt, hands it to
the harness with ``response_schema=ClusterDescribeResponse``, and then aligns
the validated entries back to the input cluster order by ``cluster_index``.
"""

import logging
from uuid import UUID

from pathlib import Path

from backend.cluster.domain import ClusterPayload
from backend.cluster.types import ClusterDescribeResponse
from backend.llm import llm_harness
from backend.llm.utils.prompts import make_prompt_loader
from backend.llm.types import LLMParseError
from backend.settings import get_config_hash, get_settings

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent.parent / "prompts" / "describer")

_STEP_TYPE = "cluster_describe"


async def describe(
    *,
    clusters_payload: list[ClusterPayload],
    user_query: str,
    reformulated_query: str,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """
    Return ``[(name, description), ...]`` aligned with *clusters_payload*.
    Args:
        clusters_payload:     List of ``ClusterPayload``, one per cluster, each
                              containing ``cluster_index``, ``top_titles``,
                              ``top_genres``, and ``sample_overviews``.
        user_query:           Oracle's original utterance.
        reformulated_query:   Enriched query from the reformulator step.
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).
        dry_run:              If ``True``, skip the live LLM and use the fixture.

    Returns:
        List of ``(name, description)`` tuples in the same order as
        *clusters_payload*.

    Raises:
        LLMParseError:     If the model returns a payload that fails
                           ``ClusterDescribeResponse`` validation on every
                           retry, or if the validated response does not cover
                           every input ``cluster_index`` exactly once.
        CostLimitExceeded: If the session budget is exhausted.
    """
    cfg = get_settings()
    config_hash = get_config_hash()
    model_and_version = cfg.models.fast.name

    system_text, prompt_hash = load_prompt(
        "cluster_describe_v2",
        {
            "clusters": clusters_payload,
            "user_query": user_query,
            "reformulated_query": reformulated_query,
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
        step_type=_STEP_TYPE,
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost_usd,
        dry_run=dry_run,
        response_schema=ClusterDescribeResponse,
    )

    # response.parsed is guaranteed non-None when response_schema is set —
    # the harness either returns a validated model or raises LLMParseError.
    assert isinstance(response.parsed, ClusterDescribeResponse)
    parsed: ClusterDescribeResponse = response.parsed

    # The model must cover every input cluster_index. Extra entries beyond the
    # requested range are tolerated (the dry-run fixture is generic and may have
    # more entries than HDBSCAN produced this turn); the lookup below drops them.
    expected = set(range(len(clusters_payload)))
    actual = {entry.cluster_index for entry in parsed.clusters}
    missing = expected - actual
    if missing:
        log.warning(
            "cluster_describer: cluster_index coverage incomplete",
            extra={
                "session_id": str(session_id),
                "expected": sorted(expected),
                "actual": sorted(actual),
                "missing": sorted(missing),
            },
        )
        raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)

    by_idx = {entry.cluster_index: entry for entry in parsed.clusters}
    result: list[tuple[str, str]] = [
        (by_idx[i].name, by_idx[i].description) for i in range(len(clusters_payload))
    ]

    log.debug(
        "cluster_describer complete",
        extra={"session_id": str(session_id), "n_clusters": len(result)},
    )
    return result
