import logging
from jinja2 import Environment, FileSystemLoader

from backend.agents.labeling.types import BatchLabelLLMResponse, BatchLabelResult
from backend.data_access.movies.queries import fetch_stubs
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

_PROMPTS_DIR = prompts_dir("labeling")
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_SENTINEL_MESSAGE_ID = "00000000-0000-0000-0000-000000000000"


async def label_clusters(
    exemplar_groups: list[list[int]],
    conversation_id: str,
    accumulated_cost: float,
    message_id: str | None = None,
) -> BatchLabelResult:
    """Generate labels and summaries for multiple clusters in a single LLM call.

    Each entry in ``exemplar_groups`` is the ordered list of exemplar movie IDs
    for one cluster (highest-probability members first). The prompt renders all
    clusters together and the LLM returns one label+summary per cluster, reducing
    round-trips compared to calling the model once per cluster.

    Args:
        exemplar_groups: List of exemplar-movie-ID lists, one per cluster to label.
                         IDs are truncated to ``cfg.labeling.top_exemplars`` per group.
        conversation_id: UUID string of the parent conversation (or ``"offline"``).
        accumulated_cost: Running LLM cost to check against limit.
        message_id:      Message UUID string for logging; a sentinel is used if omitted.

    Returns:
        ``BatchLabelResult`` with one ``LabelResult`` per input cluster group and
        the total LLM cost.

    Raises:
        LLMParseError:  If the LLM response doesn't contain the expected number of
                        cluster labels.
        CostLimitExceeded: If the accumulated cost exceeds the conversation limit.
    """
    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars

    clusters_for_prompt = []
    for group in exemplar_groups:
        stubs = fetch_stubs(group[:top_n])
        titles = [f"{s.title} ({s.release_year or '?'})" for s in stubs]
        clusters_for_prompt.append({"exemplar_titles": titles})

    template = _ENV.get_template("label_v3.j2")
    prompt = template.render(clusters=clusters_for_prompt)
    messages = [{"role": "user", "content": prompt}]

    resp = await llm_harness.call(
        run_id="offline" if conversation_id == "offline" else "online",
        conversation_id=conversation_id,
        message_id=message_id or _SENTINEL_MESSAGE_ID,
        config_hash=get_config_hash(),
        model_and_version=cfg.models.fast.name,
        provider=cfg.models.fast.provider,
        seed=cfg.models.fast.seed,
        max_tokens=cfg.models.fast.max_tokens,
        step_type="label_clusters",
        messages=messages,
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=cfg.models.fast.dry_run,
        response_schema=BatchLabelLLMResponse,
    )

    parsed: BatchLabelLLMResponse = resp.parsed  # type: ignore[assignment]
    result = BatchLabelResult.from_llm_response(parsed, n_expected=len(exemplar_groups), total_cost=resp.cost_usd)
    log.debug(
        "label_clusters_done",
        extra={"n_clusters": len(exemplar_groups), "cost_usd": resp.cost_usd},
    )
    return result
