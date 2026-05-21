import logging
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends

from backend.agents.coordinator import Coordinator
from backend.auth.types import User
from backend.data_access.conversations.queries import (
    append_message,
    create_conversation,
    get_conversation,
    get_messages,
)
from backend.exceptions import ConversationNotFound
from backend.routers.auth_deps import get_current_user
from backend.routers.dto.conversations.dtos import (
    ConversationDto,
    MessageDto,
    SendMessageRequest,
    SendMessageResponse,
)
from backend.settings import get_config_snapshot

log = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationDto, status_code=201)
async def create_new_conversation(
    user: Annotated[User | None, Depends(get_current_user)],
) -> ConversationDto:
    """Create a new conversation and return it.

    The conversation starts pointing at no cluster snapshot; the first message
    will produce the root cluster snapshot from the base clustering.

    Args:
        user: Authenticated user, or None for anonymous.

    Returns:
        ``ConversationDto`` with empty messages list.
    """
    config = get_config_snapshot()
    conversation_id = create_conversation(
        user_id=user.id if user else None,
        config_snapshot=config,
    )
    row = get_conversation(conversation_id)
    assert row is not None
    log.info("conversation_started", extra={"conversation_id": str(conversation_id)})
    return ConversationDto(
        id=row.id,
        current_cluster_snapshot_id=row.current_cluster_snapshot_id,
        messages=[],
        created_at=row.created_at,
    )


@router.get("/{conversation_id}", response_model=ConversationDto)
def get_conversation_endpoint(conversation_id: uuid.UUID) -> ConversationDto:
    """Return a conversation with its recent messages.

    Args:
        conversation_id: Conversation UUID.

    Returns:
        ``ConversationDto`` with up to 20 most recent messages.

    Raises:
        HTTPException(404): If the conversation does not exist.
    """
    row = get_conversation(conversation_id)
    if row is None:
        raise ConversationNotFound(conversation_id)
    messages = get_messages(conversation_id, limit=20)
    return ConversationDto(
        id=row.id,
        current_cluster_snapshot_id=row.current_cluster_snapshot_id,
        messages=[
            MessageDto(id=m.id, role=m.role, content=m.content, created_at=m.created_at)
            for m in messages
        ],
        created_at=row.created_at,
    )


@router.post("/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    user: Annotated[User | None, Depends(get_current_user)],
) -> SendMessageResponse:
    """Process a user message and return the assistant reply with updated cluster snapshot.

    Args:
        conversation_id: Conversation UUID.
        body:            Request body with user message content.
        user:            Authenticated user, or None for anonymous.

    Returns:
        ``SendMessageResponse`` with assistant reply and new cluster snapshot ID.

    Raises:
        HTTPException(404): If the conversation does not exist.
        HTTPException(422): If the coordinator cannot process the message.
    """
    row = get_conversation(conversation_id)
    if row is None:
        raise ConversationNotFound(conversation_id)

    append_message(conversation_id, "user", body.content)
    log.info("user_message", extra={"conversation_id": str(conversation_id)})

    coordinator = Coordinator()
    result = await coordinator.handle_message(
        conversation_id=conversation_id,
        user_message=body.content,
        conversation_row=row,
    )

    msg_id = append_message(conversation_id, "assistant", result.reply_text)
    log.info("assistant_reply", extra={"conversation_id": str(conversation_id), "cluster_snapshot_id": str(result.cluster_snapshot_id)})

    return SendMessageResponse(
        message=MessageDto(
            id=msg_id,
            role="assistant",
            content=result.reply_text,
            created_at=row.created_at,
        ),
        cluster_snapshot_id=result.cluster_snapshot_id,
    )
