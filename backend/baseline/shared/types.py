import uuid
from dataclasses import dataclass, field

from backend.coordinator.types import TurnTrace


@dataclass(frozen=True, slots=True)
class SystemTurnResult:
    """Output of one system turn, common across all three conditions.

    Attributes:
        reply_text:          Text to send back to the oracle.
        cluster_snapshot_id: UUID of the active cluster snapshot after this turn.
        turn_cost_usd:       LLM cost incurred during this turn.
        suggestion:          Optional follow-up suggestion text.
        turn_trace:          Structured intent trace for turn_intents persistence.
    """
    reply_text: str
    cluster_snapshot_id: uuid.UUID
    turn_cost_usd: float = 0.0
    suggestion: str | None = None
    turn_trace: TurnTrace | None = None
