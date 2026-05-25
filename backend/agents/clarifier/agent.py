import logging
import uuid
from jinja2 import Environment, FileSystemLoader

from backend.agents.clarifier.types import ClarifierResult
from backend.agents.intent.types import IntentAction
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

_PROMPTS_DIR = prompts_dir("clarifier")
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def clarify(
    user_message: str,
    clusters: list[ClusterRow],
    action: IntentAction,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
) -> ClarifierResult:
    """Generate a disambiguation question when intent confidence is below threshold.

    Does not modify any cluster state. The question is returned to the user so they
    can restate their request more precisely.

    Args:
        user_message:     Original user message that produced the low-confidence intent.
        clusters:         Current cluster list (labels used for context in the prompt).
        action:           The specific low-confidence action — guessed mode, concept, target.
        conversation_id:  Conversation UUID for logging.
        message_id:       Current message UUID for logging.
        accumulated_cost: Running LLM cost this conversation.

    Returns:
        ``ClarifierResult`` with the disambiguation question text and call cost.
    """
    cfg = get_settings()

    guessed_target_label: str | None = None
    if action.target_cluster_id is not None:
        match = next((c for c in clusters if c.id == action.target_cluster_id), None)
        if match:
            guessed_target_label = match.label

    template = _ENV.get_template("clarify_v1.j2")
    prompt = template.render(
        clusters=[{"label": c.label or "Unlabeled"} for c in clusters],
        user_message=user_message,
        guessed_mode=action.navigationMode.value,
        guessed_concept=action.concept,
        guessed_target_label=guessed_target_label,
        confidence=action.confidence,
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
        step_type="clarifier_agent",
        messages=messages,
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=cfg.models.fast.dry_run,
    )

    result = ClarifierResult.from_llm_response(resp.content, cost=resp.cost_usd)
    log.info(
        "clarifier_generated",
        extra={
            "conversation_id": str(conversation_id),
            "low_confidence_mode": action.navigationMode.value,
            "confidence": action.confidence,
        },
    )
    return result
