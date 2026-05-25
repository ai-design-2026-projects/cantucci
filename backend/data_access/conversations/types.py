import uuid
from dataclasses import dataclass
from datetime import datetime



@dataclass(frozen=True, slots=True)
class ConversationRow:
    """A row from the conversations table.

    Attributes:
        id:                   Conversation UUID.
        user_id:              Owner user UUID, or None for anonymous.
        current_cluster_snapshot_id: UUID of the cluster snapshot currently displayed.
        config_snapshot:             YAML config dict at conversation creation time.
        created_at:                  UTC creation timestamp.
        accumulated_cost_usd:        Running total LLM cost across all turns, in USD.
    """
    id: uuid.UUID
    user_id: uuid.UUID | None
    current_cluster_snapshot_id: uuid.UUID | None
    config_snapshot: dict
    created_at: datetime
    accumulated_cost_usd: float = 0.0

    @classmethod
    def from_row(cls, r: dict) -> "ConversationRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            user_id=r["user_id"],
            current_cluster_snapshot_id=r["current_cluster_snapshot_id"],
            config_snapshot=r["config_snapshot"],
            created_at=r["created_at"],
            accumulated_cost_usd=r["accumulated_cost_usd"],
        )


@dataclass(frozen=True, slots=True)
class MessageRow:
    """A row from the messages table.

    Attributes:
        id:              Message UUID.
        conversation_id: Parent conversation UUID.
        role:            ``"user"`` or ``"assistant"``.
        content:         Message text.
        created_at:      UTC creation timestamp.
        cost_usd:        LLM cost in USD for the turn this message represents (0 for user messages).
    """
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    cost_usd: float = 0.0

    @classmethod
    def from_row(cls, r: dict) -> "MessageRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            conversation_id=r["conversation_id"],
            role=r["role"],
            content=r["content"],
            created_at=r["created_at"],
            cost_usd=r["cost_usd"],
        )
