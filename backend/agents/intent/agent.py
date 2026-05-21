import logging
import uuid

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from backend.agents.intent.types import IntentResult
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

_PROMPTS_DIR = prompts_dir("intent")
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


class _IntentLLMResponse(BaseModel):
    """Structured output expected from the intent classification LLM call."""
    mode: str
    concept: str | None = None
    merged_label: str | None = None
    target_cluster_id: str | None = None
    confidence: float = 1.0


async def classify(
    user_message: str,
    clusters: list[ClusterRow],
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
) -> IntentResult:
    """Classify the user's intent from their message and the current cluster state.

    Args:
        user_message:    Raw user message text.
        clusters:        Current cluster snapshot's cluster list (for context).
        conversation_id: Parent conversation UUID for logging.
        message_id:      Current message UUID for logging.
        accumulated_cost: Running LLM cost this conversation.

    Returns:
        ``IntentResult`` with classified mode, dimension, and target cluster.
    """
    cfg = get_settings()

    template = _ENV.get_template("intent_v1.j2")
    prompt = template.render(
        clusters=[{"id": str(c.id), "label": c.label} for c in clusters],
        user_message=user_message,
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
        step_type="intent_agent",
        messages=messages,
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=cfg.models.fast.dry_run,
        response_schema=_IntentLLMResponse,
    )

    parsed: _IntentLLMResponse = resp.parsed  # type: ignore[assignment]
    result = IntentResult.from_llm_response(parsed, raw_content=resp.content)
    log.info(
        "intent_classified",
        extra={
            "conversation_id": str(conversation_id),
            "mode": result.mode.value,
            "concept": result.concept,
            "confidence": result.confidence,
        },
    )
    return result
