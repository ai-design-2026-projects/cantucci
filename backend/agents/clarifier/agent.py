import logging
from typing import Any

from backend.agents.base import LLMAgent
from backend.agents.clarifier.types import ClarifierResult
from backend.agents.intent.types import IntentAction
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.llm.types import LLMResponse

log = logging.getLogger(__name__)


class ClarifierLLMAgent(LLMAgent[ClarifierResult]):
    """Generates a disambiguation question when intent confidence is below threshold."""

    name = "clarifier"
    step_type = "clarifier_agent"
    model_tier = "fast"
    template_name = "clarify_v1.j2"
    response_schema = None

    async def render_kwargs(self, **inputs: Any) -> dict[str, Any]:
        action: IntentAction = inputs["action"]
        clusters: list[ClusterRow] = inputs["clusters"]
        guessed_target_label: str | None = None
        if action.target_cluster_id is not None:
            match = next((c for c in clusters if c.id == action.target_cluster_id), None)
            if match:
                guessed_target_label = match.label
        return {
            "clusters": [{"label": c.label or "Unlabeled"} for c in clusters],
            "user_message": inputs["user_message"],
            "guessed_mode": action.mode.value,
            "guessed_concept": action.concept,
            "guessed_target_label": guessed_target_label,
            "confidence": action.confidence,
        }

    def build_result(self, resp: LLMResponse, **inputs: Any) -> ClarifierResult:
        action: IntentAction = inputs["action"]
        result = ClarifierResult.from_llm_response(resp.content, cost=resp.cost_usd)
        log.info(
            "clarifier_generated",
            extra={
                "conversation_id": str(inputs["conversation_id"]),
                "low_confidence_mode": action.mode.value,
                "confidence": action.confidence,
            },
        )
        return result


agent = ClarifierLLMAgent()
