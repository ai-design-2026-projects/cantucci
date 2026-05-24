import logging
import uuid
from jinja2 import Environment, FileSystemLoader

from backend.agents.suggester.types import SuggesterLLMResponse, SuggestionResult
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

_PROMPTS_DIR = prompts_dir("suggester")
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def suggest(
    last_operation: str,
    clusters: list[ClusterRow],
    signals: list[str],
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
) -> SuggestionResult:
    """Generate a natural-language follow-up suggestion from deterministic signals.

    Only called when at least one signal exceeds its configured threshold. If the
    model decides none of the signals warrant a suggestion it returns ``text=None``.

    Args:
        last_operation:   Human-readable summary of the operation just completed
                          (e.g. ``"Split 'Action' into 4 sub-clusters"``).
        clusters:         Cluster list of the resulting snapshot (labels + summaries).
        signals:          Pre-ranked list of human-readable signal descriptions to
                          pass to the model (at most ``cfg.suggestions.top_n_signals``).
        conversation_id:  Conversation UUID for logging.
        message_id:       Current message UUID for logging.
        accumulated_cost: Running LLM cost this conversation.

    Returns:
        ``SuggestionResult`` with optional suggestion text and call cost.
    """
    cfg = get_settings()

    template = _ENV.get_template("suggest_v1.j2")
    prompt = template.render(
        last_operation=last_operation,
        clusters=[
            {"label": c.label or "Unlabeled", "summary": c.summary}
            for c in clusters
        ],
        signals=signals,
    )
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
        step_type="suggester_agent",
        messages=messages,
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=cfg.models.fast.dry_run,
        response_schema=SuggesterLLMResponse,
    )

    parsed: SuggesterLLMResponse = resp.parsed  # type: ignore[assignment]
    result = SuggestionResult.from_llm_response(parsed, cost=resp.cost_usd)
    log.info(
        "suggestion_generated",
        extra={
            "conversation_id": str(conversation_id),
            "has_suggestion": result.text is not None,
            "n_signals": len(signals),
        },
    )
    return result
