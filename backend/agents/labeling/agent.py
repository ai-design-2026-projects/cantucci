import logging
import uuid

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from backend.agents.labeling.types import LabelResult
from backend.data_access.movies.queries import fetch_stubs
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

_PROMPTS_DIR = prompts_dir("labeling")
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_TOP_EXEMPLARS = 15
_SENTINEL_MESSAGE_ID = "00000000-0000-0000-0000-000000000000"


class _LabelLLMResponse(BaseModel):
    """Structured output expected from the labeling LLM call."""
    label: str
    summary: str


async def label_cluster(
    exemplar_movie_ids: list[int],
    conversation_id: str,
    accumulated_cost: float,
    message_id: str | None = None,
) -> LabelResult:
    """Generate a label and summary for a cluster using its exemplar movies.

    Args:
        exemplar_movie_ids: Top movie IDs from the cluster (by membership probability).
        conversation_id:    UUID string of the parent conversation (or ``"offline"``).
        accumulated_cost:   Running LLM cost to check against limit.
        message_id:         Message UUID string for logging; a sentinel is used if omitted.

    Returns:
        ``LabelResult`` with label and summary. Falls back to generic strings on any error.
    """
    cfg = get_settings()

    stubs = fetch_stubs(exemplar_movie_ids[:_TOP_EXEMPLARS])
    if not stubs:
        return LabelResult(label="Unnamed Cluster", summary=None)

    exemplar_titles = [f"{s.title} ({s.release_year or '?'})" for s in stubs]
    template = _ENV.get_template("label_v1.j2")
    prompt = template.render(exemplar_titles=exemplar_titles)
    messages = [{"role": "user", "content": prompt}]

    try:
        resp = await llm_harness.call(
            run_id="offline" if conversation_id == "offline" else "online",
            conversation_id=conversation_id,
            message_id=message_id or _SENTINEL_MESSAGE_ID,
            config_hash=get_config_hash(),
            model_and_version=cfg.models.fast.name,
            provider=cfg.models.fast.provider,
            seed=cfg.models.fast.seed,
            max_tokens=cfg.models.fast.max_tokens,
            step_type="label_cluster",
            messages=messages,
            cost_limit_usd=cfg.conversation.cost_limit_usd,
            accumulated_cost_usd=accumulated_cost,
            dry_run=cfg.models.fast.dry_run,
            response_schema=_LabelLLMResponse,
        )
        parsed: _LabelLLMResponse = resp.parsed  # type: ignore[assignment]
        result = LabelResult.from_llm_response(parsed)
        log.debug("label_cluster_done", extra={"label": result.label, "n_exemplars": len(exemplar_movie_ids)})
        return result
    except Exception as exc:
        log.warning("label_cluster_failed", extra={"error": str(exc), "n_exemplars": len(exemplar_movie_ids)})
        return LabelResult(label="Unnamed Cluster", summary=None)
