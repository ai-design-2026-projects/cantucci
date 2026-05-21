import logging
import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from backend.agents.intent.types import IntentResult, NavigationMode
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.llm import llm_harness
from backend.llm.prompts import hash_messages
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

_PROMPTS_DIR = prompts_dir("intent")
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


class _IntentLLMResponse(BaseModel):
    """Structured output expected from the intent classification LLM call."""
    mode: str
    dimension: str | None = None
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
    prompt_hash = hash_messages(messages)

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
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=cfg.models.fast.dry_run,
        response_schema=_IntentLLMResponse,
    )

    parsed: _IntentLLMResponse = resp.parsed  # type: ignore[assignment]

    try:
        mode = NavigationMode(parsed.mode)
    except ValueError:
        log.warning("intent_unknown_mode", extra={"raw_mode": parsed.mode})
        mode = NavigationMode.SMALL_TALK

    target_id: uuid.UUID | None = None
    if parsed.target_cluster_id:
        try:
            target_id = uuid.UUID(parsed.target_cluster_id)
        except ValueError:
            log.warning("intent_invalid_cluster_id", extra={"raw": parsed.target_cluster_id})

    result = IntentResult(
        mode=mode,
        dimension=parsed.dimension,
        target_cluster_id=target_id,
        confidence=parsed.confidence,
        raw_intent=resp.content,
    )
    log.info(
        "intent_classified",
        extra={
            "conversation_id": str(conversation_id),
            "mode": mode.value,
            "dimension": parsed.dimension,
            "confidence": parsed.confidence,
        },
    )
    return result
