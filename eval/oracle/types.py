from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from backend.llm.exceptions import LLMParseError


class OracleLLMResponse(BaseModel):
    """Structured output from a single oracle turn.

    Attributes:
        message: The oracle's reply text to send to the system.
        intent:  High-level intent of the reply.
    """
    message: str
    intent: Literal["continue", "accept", "abandon"]


@dataclass(frozen=True, slots=True)
class OracleTurnResult:
    """Result of one oracle turn.

    Attributes:
        message: Oracle reply text.
        intent:  Parsed intent (continue | accept | abandon).
        cost:    LLM cost in USD for this call.
    """
    message: str
    intent: str
    cost: float

    @classmethod
    def from_llm_response(cls, parsed: OracleLLMResponse, cost: float) -> "OracleTurnResult":
        """Construct from a structured LLM response.

        Args:
            parsed: Pydantic-validated oracle LLM payload.
            cost:   LLM cost in USD.

        Raises:
            LLMParseError: If intent is not a recognised value.
        """
        if parsed.intent not in ("continue", "accept", "abandon"):
            raise LLMParseError(
                step_type="oracle_turn",
                raw=f"invalid intent: {parsed.intent!r}",
            )
        return cls(message=parsed.message, intent=parsed.intent, cost=cost)
