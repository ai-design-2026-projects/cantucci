import logging
from typing import Any

from backend.agents.base import LLMAgent
from backend.agents.concept.parser import parse_concept
from backend.agents.concept.types import ConceptLLMResponse, ConceptRep
from backend.llm.types import LLMResponse

log = logging.getLogger(__name__)


class ConceptLLMAgent(LLMAgent[ConceptRep]):
    """Parses a concept string and builds its embedding-space representation."""

    name = "concept"
    step_type = "concept_agent"
    model_tier = "strong"
    template_name = "parse_v5.j2"
    response_schema = ConceptLLMResponse

    async def render_kwargs(self, **inputs: Any) -> dict[str, Any]:
        return {"concept": inputs["concept_name"]}

    def build_result(self, resp: LLMResponse, **inputs: Any) -> ConceptRep:
        parsed: ConceptLLMResponse = resp.parsed  # type: ignore[assignment]
        concept = parse_concept(parsed, inputs["concept_name"], cost=resp.cost_usd)
        log.info(
            "concept_built",
            extra={
                "concept": inputs["concept_name"],
                "type": parsed.type,
                "cost_usd": resp.cost_usd,
            },
        )
        return concept


agent = ConceptLLMAgent()
