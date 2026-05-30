import logging
from typing import Any

from backend.agents.base import LLMAgent
from backend.agents.intent.types import (
    DialogueMode,
    IntentResult,
    NavigationMode,
)
from backend.agents.intent.wire import IntentLLMResponse
from backend.llm.types import LLMResponse

log = logging.getLogger(__name__)


class IntentLLMAgent(LLMAgent[IntentResult]):
    """Classifies user intent from their message and the current cluster state."""

    name = "intent"
    step_type = "intent_agent"
    model_tier = "strong"
    template_name = "intent_v11.j2"
    response_schema = IntentLLMResponse

    async def render_kwargs(self, **inputs: Any) -> dict[str, Any]:
        modes = [(m.value, m.description) for m in (*NavigationMode, *DialogueMode)]
        return {
            "clusters": [
                {"id": str(c.id), "label": c.label} for c in inputs["clusters"]
            ],
            "user_message": inputs["user_message"],
            "modes": modes,
            "clarification_question": inputs.get("clarification_question"),
        }

    def build_result(self, resp: LLMResponse, **inputs: Any) -> IntentResult:
        parsed: IntentLLMResponse = resp.parsed  # type: ignore[assignment]
        log.debug("intent_reasoning", extra={"reasoning": parsed.reasoning})
        result = IntentResult.from_llm_response(parsed, raw_content=resp.content, cost=resp.cost_usd)
        log.info(
            "intent_classified",
            extra={
                "conversation_id": str(inputs["conversation_id"]),
                "n_actions": len(result.actions),
                "navigation_modes": [a.mode.value for a in result.actions],
            },
        )
        return result


agent = IntentLLMAgent()
