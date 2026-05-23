import uuid
from datetime import datetime

from pydantic import BaseModel


class CreateConversationRequest(BaseModel):
    """Body for ``POST /conversations``.

    No fields required — the server assigns user from the auth token and
    records the active config snapshot automatically.
    """


class UpdateConversationRequest(BaseModel):
    """Body for ``PATCH /conversations/{id}``.

    Attributes:
        current_cluster_snapshot_id: New active cluster snapshot UUID.
    """
    current_cluster_snapshot_id: uuid.UUID


class SendMessageRequest(BaseModel):
    """Body for ``POST /conversations/{id}/messages``.

    Attributes:
        content: User message text.
    """
    content: str


class MessageDto(BaseModel):
    """A single conversation message.

    Attributes:
        id:         Message UUID.
        role:       ``"user"`` or ``"assistant"``.
        content:    Message text.
        created_at: UTC timestamp.
        suggestion: Optional follow-up suggestion from the suggester agent.
                    Present only on assistant messages produced after a state-changing
                    operation; None for clarification replies, small_talk, and explain.
    """
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    suggestion: str | None = None


class ConversationDto(BaseModel):
    """Full conversation with recent messages.

    Attributes:
        id:                          Conversation UUID.
        current_cluster_snapshot_id: UUID of the currently active cluster snapshot.
        messages:                    Most recent messages (oldest first).
        created_at:                  UTC creation timestamp.
    """
    id: uuid.UUID
    current_cluster_snapshot_id: uuid.UUID | None
    messages: list[MessageDto]
    created_at: datetime


class SendMessageResponse(BaseModel):
    """Response for ``POST /conversations/{id}/messages``.

    Attributes:
        message:             The assistant reply message.
        cluster_snapshot_id: UUID of the new or updated cluster snapshot.
    """
    message: MessageDto
    cluster_snapshot_id: uuid.UUID
