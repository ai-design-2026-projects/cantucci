import logging
from typing import Any

from backend.agents.base import LLMAgent
from backend.agents.responder.types import ResponderLLMResponse, SuggestionResult
from backend.llm.types import LLMResponse

log = logging.getLogger(__name__)


class ResponderLLMAgent(LLMAgent[SuggestionResult]):
    """Generates a natural-language follow-up suggestion from deterministic signals."""

    name = "responder"
    step_type = "responder_agent"
    model_tier = "fast"
    template_name = "suggest_v1.j2"
    response_schema = ResponderLLMResponse

    async def render_kwargs(self, **inputs: Any) -> dict[str, Any]:
        return {
            "last_operation": inputs["last_operation"],
            "clusters": [
                {"label": c.label or "Unlabeled", "summary": c.summary}
                for c in inputs["clusters"]
            ],
            "signals": inputs["signals"],
        }

    def build_result(self, resp: LLMResponse, **inputs: Any) -> SuggestionResult:
        parsed: ResponderLLMResponse = resp.parsed  # type: ignore[assignment]
        result = SuggestionResult.from_llm_response(parsed, cost=resp.cost_usd)
        log.info(
            "suggestion_generated",
            extra={
                "conversation_id": str(inputs["conversation_id"]),
                "has_suggestion": result.text is not None,
                "n_signals": len(inputs["signals"]),
            },
        )
        return result


agent = ResponderLLMAgent()
