import logging
from dataclasses import dataclass

from backend.data_access.movies.queries import fetch_stubs
from backend.llm import llm_harness
from backend.llm.prompts import hash_messages
from backend.settings import get_config_hash, get_settings

log = logging.getLogger(__name__)

_LABEL_SYSTEM = (
    "You label movie clusters. Given a list of exemplar movie titles, "
    "produce a short label (2–4 words) and a one-sentence description of "
    "the semantic theme. Respond as JSON: {\"label\": \"...\", \"summary\": \"...\"}"
)

_SENTINEL_RUN_ID = "offline"
_SENTINEL_MESSAGE_ID = "00000000-0000-0000-0000-000000000000"


async def label_cluster(
    exemplar_movie_ids: list[int],
    conversation_id: str,
    accumulated_cost: float,
) -> tuple[str, str]:
    """Generate a label and summary for a cluster using its exemplar movies.

    Args:
        exemplar_movie_ids: Top movie IDs from the cluster (by membership probability).
        conversation_id:    UUID string of the parent conversation (or ``"offline"``).
        accumulated_cost:   Running LLM cost to check against limit.

    Returns:
        Tuple of (label, summary). Falls back to generic strings on any error.
    """
    cfg = get_settings()

    stubs = fetch_stubs(exemplar_movie_ids[:15])
    if not stubs:
        return "Unnamed Cluster", None

    titles_text = "\n".join(f"- {s.title} ({s.release_year or '?'})" for s in stubs)
    messages = [
        {"role": "system", "content": _LABEL_SYSTEM},
        {"role": "user", "content": f"Exemplar movies:\n{titles_text}"},
    ]
    prompt_hash = hash_messages(messages)

    try:
        from pydantic import BaseModel

        class _LabelResponse(BaseModel):
            label: str
            summary: str

        resp = await llm_harness.call(
            run_id=_SENTINEL_RUN_ID,
            conversation_id=conversation_id,
            message_id=_SENTINEL_MESSAGE_ID,
            config_hash=get_config_hash(),
            model_and_version=cfg.models.fast.name,
            provider=cfg.models.fast.provider,
            seed=cfg.models.fast.seed,
            max_tokens=cfg.models.fast.max_tokens,
            step_type="label_cluster",
            messages=messages,
            prompt_hash=prompt_hash,
            cost_limit_usd=cfg.conversation.cost_limit_usd,
            accumulated_cost_usd=accumulated_cost,
            dry_run=cfg.models.fast.dry_run,
            response_schema=_LabelResponse,
        )
        parsed: _LabelResponse = resp.parsed  # type: ignore[assignment]
        return parsed.label, parsed.summary
    except Exception as exc:
        log.warning("label_cluster_failed", extra={"error": str(exc), "n_exemplars": len(exemplar_movie_ids)})
        return "Unnamed Cluster", None
