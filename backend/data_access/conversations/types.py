import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ConversationRow:
    """A row from the conversations table.

    Attributes:
        id:                   Conversation UUID.
        user_id:              Owner user UUID, or None for anonymous.
        current_cluster_snapshot_id: UUID of the cluster snapshot currently displayed.
        config_snapshot:             YAML config dict at conversation creation time.
        created_at:                  UTC creation timestamp.
    """
    id: uuid.UUID
    user_id: uuid.UUID | None
    current_cluster_snapshot_id: uuid.UUID | None
    config_snapshot: dict
    created_at: datetime


@dataclass
class MessageRow:
    """A row from the messages table.

    Attributes:
        id:              Message UUID.
        conversation_id: Parent conversation UUID.
        role:            ``"user"`` or ``"assistant"``.
        content:         Message text.
        created_at:      UTC creation timestamp.
    """
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    created_at: datetime
