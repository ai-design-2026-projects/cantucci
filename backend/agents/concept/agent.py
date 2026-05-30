import logging
from typing import Any

from backend.agents.base import LLMAgent
from backend.agents.concept.parser import build_linear_axis
from backend.agents.concept.types import ConceptLLMResponse, LinearAxisRep
from backend.llm.types import LLMResponse

log = logging.getLogger(__name__)


class ConceptLLMAgent(LLMAgent[LinearAxisRep]):
    """Parses a concept string and builds its embedding-space representation."""

    name = "concept"
    step_type = "concept_agent"
    model_tier = "strong"
    template_name = "parse_v6.j2"
    response_schema = ConceptLLMResponse

    async def render_kwargs(self, **inputs: Any) -> dict[str, Any]:
        return {"concept": inputs["concept_name"]}

    def build_result(self, resp: LLMResponse, **inputs: Any) -> LinearAxisRep:
        parsed: ConceptLLMResponse = resp.parsed  # type: ignore[assignment]
        concept = build_linear_axis(parsed, inputs["concept_name"], cost=resp.cost_usd)
        log.info(
            "concept_built",
            extra={
                "concept": inputs["concept_name"],
                "space": parsed.space,
                "cost_usd": resp.cost_usd,
            },
        )
        return concept


agent = ConceptLLMAgent()
