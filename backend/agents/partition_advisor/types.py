from dataclasses import dataclass

from pydantic import BaseModel

from backend.agents.clustering.types import PartitionBin


class ProposedBinLLM(BaseModel):
    """A single labelled bin returned by the partition advisor LLM."""

    label: str
    min: float | None = None
    max: float | None = None


class PartitionAdvisorLLMResponse(BaseModel):
    """Structured output from the partition advisor LLM call.

    Attributes:
        bins: Ordered list of proposed bins covering the full attribute range.
    """

    bins: list[ProposedBinLLM]


@dataclass(frozen=True, slots=True)
class PartitionAdvisorResult:
    """Output of the partition advisor agent.

    Attributes:
        bins: Proposed ``PartitionBin`` objects in order, ready to pass to
              ``partition_by`` after user confirmation.
        cost: LLM cost in USD for this call.
    """

    bins: list[PartitionBin]
    cost: float

    @classmethod
    def from_llm_response(
        cls, parsed: PartitionAdvisorLLMResponse, cost: float
    ) -> "PartitionAdvisorResult":
        """Construct from a structured LLM response.

        Args:
            parsed: Pydantic-validated LLM payload.
            cost:   LLM call cost in USD.
        """
        return cls(
            bins=[PartitionBin(label=b.label, min=b.min, max=b.max) for b in parsed.bins],
            cost=cost,
        )
