from dataclasses import dataclass

from pydantic import BaseModel


class SuggesterLLMResponse(BaseModel):
    """Structured output expected from the suggester LLM call.

    Attributes:
        text: A 1–2 sentence suggestion for the user's next move, or null if
              no meaningful suggestion can be produced from the available signals.
    """
    text: str | None = None


@dataclass(frozen=True, slots=True)
class SuggestionResult:
    """Output of the Suggester agent.

    Attributes:
        text: Suggestion text to surface to the user, or None if signals did not
              produce a useful follow-up.
        cost: LLM cost in USD for this call (0.0 when the LLM was skipped).
    """
    text: str | None
    cost: float

    @classmethod
    def from_llm_response(cls, parsed: SuggesterLLMResponse, cost: float) -> "SuggestionResult":
        """Construct from a structured LLM response.

        Args:
            parsed: Pydantic-validated LLM payload.
            cost:   LLM cost in USD.
        """
        return cls(text=parsed.text, cost=cost)
