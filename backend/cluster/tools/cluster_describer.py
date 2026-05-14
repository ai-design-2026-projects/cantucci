"""cluster_describer — assign a name and description to each cluster via LLM.

A single batched call sends all clusters' top titles, genres, and overviews to
the model, which returns a JSON list of {name, description} pairs.  One call
per turn is cheaper and lets the model differentiate cluster names by contrast.
"""

import json
import logging
from uuid import UUID

from pathlib import Path

from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.llm.types import LLMParseError
from backend.settings import get_settings

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent.parent / "prompts")

_STEP_TYPE = "cluster_describe"


def describe(
    *,
    clusters_payload: list[dict],
    user_query: str,
    reformulated_query: str,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    config_hash: str,
    model_version: str,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """Return ``[(name, description), ...]`` aligned with *clusters_payload*.

    On ``dry_run=True``, returns synthetic placeholder names without an LLM call.

    Args:
        clusters_payload:     List of dicts, one per cluster, each containing
                              ``cluster_index``, ``top_titles``, ``top_genres``,
                              and ``sample_overviews``.
        user_query:           Oracle's original utterance.
        reformulated_query:   Enriched query from the reformulator step.
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        config_hash:          SHA-256 prefix of the session's YAML config snapshot.
        model_version:        LLM model string stored on the session row.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).
        dry_run:              If ``True``, return placeholder names without LLM call.

    Returns:
        List of ``(name, description)`` tuples in the same order as
        *clusters_payload*.

    Raises:
        LLMParseError:     If the model returns non-JSON, a non-list, or a list
                           of the wrong length.
        CostLimitExceeded: If the session budget is exhausted.
    """
    if dry_run:
        return [
            (f"Cluster {item['cluster_index']}", "dry-run description")
            for item in clusters_payload
        ]

    cfg = get_settings()

    system_text, prompt_hash = load_prompt(
        "cluster_describe_v1",
        {
            "clusters": clusters_payload,
            "user_query": user_query,
            "reformulated_query": reformulated_query,
        },
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_text},
        {
            "role": "user",
            "content": (
                f"Original query: {user_query}\n"
                f"Enriched query: {reformulated_query}\n\n"
                f"Clusters to name: {json.dumps(clusters_payload)}"
            ),
        },
    ]

    response = llm_harness.call(
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        config_hash=config_hash,
        model_and_version=model_version,
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

    if not isinstance(parsed, list):
        raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)

    if len(parsed) != len(clusters_payload):
        raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)

    result: list[tuple[str, str]] = []
    for entry in parsed:
        if not isinstance(entry.get("name"), str) or not isinstance(
            entry.get("description"), str
        ):
            raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)
        result.append((entry["name"], entry["description"]))

    log.debug(
        "cluster_describer complete",
        extra={"session_id": str(session_id), "n_clusters": len(result)},
    )
    return result
