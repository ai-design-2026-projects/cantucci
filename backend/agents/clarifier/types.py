from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClarifierResult:
    """Output of the Clarifier agent.

    Attributes:
        text: A short disambiguation question to return to the user.
        cost: LLM cost in USD for this call.
    """
    text: str
    cost: float

    @classmethod
    def from_llm_response(cls, content: str, cost: float) -> "ClarifierResult":
        """Construct from a plain-text LLM response.

        Args:
            content: Raw text produced by the model.
            cost:    LLM cost in USD.
        """
        return cls(text=content.strip(), cost=cost)
