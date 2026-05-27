from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from backend.llm.exceptions import LLMParseError


class OracleLLMResponse(BaseModel):
    """Structured output from a single oracle turn.

    Attributes:
        message:        The oracle's reply text to send to the system.
        decision:       Whether to continue or stop the session.
        rationale:      Free-text explanation of the decision.
        session_rating: 1–5 overall session rating; required when decision is "stop".
    """
    message: str
    decision: Literal["stop", "continue"]
    rationale: str
    session_rating: int | None = None


@dataclass(frozen=True, slots=True)
class OracleTurnResult:
    """Result of one oracle turn.

    Attributes:
        message:        Oracle reply text.
        decision:       "stop" or "continue".
        rationale:      Free-text rationale for the decision.
        session_rating: 1–5 rating emitted at stop; None while continuing.
        cost:           LLM cost in USD for this call.
    """
    message: str
    decision: str
    rationale: str
    session_rating: int | None
    cost: float

    @classmethod
    def from_llm_response(cls, parsed: OracleLLMResponse, cost: float) -> "OracleTurnResult":
        """Construct from a structured LLM response.

        Args:
            parsed: Pydantic-validated oracle LLM payload.
            cost:   LLM cost in USD.

        Raises:
            LLMParseError: If session_rating is out of range when decision is "stop".
        """
        if parsed.decision == "stop" and parsed.session_rating is None:
            raise LLMParseError(
                step_type="oracle_turn",
                raw="session_rating is required when decision is 'stop'",
            )
        if parsed.session_rating is not None and not (1 <= parsed.session_rating <= 5):
            raise LLMParseError(
                step_type="oracle_turn",
                raw=f"session_rating {parsed.session_rating} out of range [1, 5]",
            )
        return cls(
            message=parsed.message,
            decision=parsed.decision,
            rationale=parsed.rationale,
            session_rating=parsed.session_rating,
            cost=cost,
        )
