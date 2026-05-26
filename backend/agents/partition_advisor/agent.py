import logging
import uuid

from jinja2 import Environment, FileSystemLoader

from backend.agents.partition_advisor.types import PartitionAdvisorLLMResponse, PartitionAdvisorResult
from backend.data_access.movies.types import NumericStats
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

_PROMPTS_DIR = prompts_dir("partition_advisor")
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def propose_bins(
    attribute: str,
    stats: NumericStats,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
) -> PartitionAdvisorResult:
    """Propose 3–4 labelled bins for a numeric partition attribute based on distribution stats.

    Called when the user requests a numeric ``partition_by`` without specifying bin
    thresholds. The result is shown to the user as a proposal; no cluster state is
    modified until the user confirms.

    Args:
        attribute:        Partition attribute name — one of ``"runtime"``,
                          ``"release_year"``, or ``"vote_average"``.
        stats:            Distribution statistics for the attribute within the
                          in-scope movie set.
        conversation_id:  Conversation UUID for logging.
        message_id:       Current message UUID for logging.
        accumulated_cost: Running LLM cost this conversation.

    Returns:
        ``PartitionAdvisorResult`` with proposed bins and call cost.
    """
    cfg = get_settings()

    template = _ENV.get_template("propose_bins_v1.j2")
    prompt = template.render(
        attribute=attribute,
        min_val=stats.min_val,
        max_val=stats.max_val,
        p25=stats.p25,
        p50=stats.p50,
        p75=stats.p75,
        count=stats.count,
    )
    log.debug("llm_prompt", extra={"template": "propose_bins_v1.j2", "prompt": prompt})
    messages = [{"role": "user", "content": prompt}]

    resp = await llm_harness.call(
        run_id="online",
        conversation_id=str(conversation_id),
        message_id=str(message_id),
        config_hash=get_config_hash(),
        model_and_version=cfg.models.fast.name,
        provider=cfg.models.fast.provider,
        seed=cfg.models.fast.seed,
        max_tokens=cfg.models.fast.max_tokens,
        step_type="partition_advisor",
        messages=messages,
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=cfg.models.fast.dry_run,
        response_schema=PartitionAdvisorLLMResponse,
    )
    log.debug("llm_response", extra={"step_type": "partition_advisor", "content": resp.content})

    parsed: PartitionAdvisorLLMResponse = resp.parsed  # type: ignore[assignment]
    result = PartitionAdvisorResult.from_llm_response(parsed, cost=resp.cost_usd)
    log.info(
        "partition_advisor_proposed",
        extra={
            "conversation_id": str(conversation_id),
            "attribute": attribute,
            "n_bins": len(result.bins),
            "bin_labels": [b.label for b in result.bins],
        },
    )
    return result
