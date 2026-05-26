import asyncio
import json
import logging
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.agents.coordinator.agent import Coordinator
from backend.auth.types import User
from backend.data_access.conversations.queries import (
    add_conversation_cost,
    append_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_messages,
    list_conversations_for_user,
    set_current_cluster_snapshot,
)
from backend.data_access.cluster_snapshots.queries import (
    get_cluster_snapshot,
    record_conversation_snapshot_ref,
)
from backend.exceptions import ClusterSnapshotNotFound, ConversationNotFound, NotConversationOwner
from backend.agents.coordinator.tools.progress import register_queue, unregister_queue
from backend.routers.auth_deps import get_current_user
from backend.routers.dto.conversations.dtos import (
    ConversationDto,
    MessageDto,
    SendMessageRequest,
    SendMessageResponse,
    UpdateConversationRequest,
)
from backend.settings import get_config_snapshot
import demo.chat_record_replay as _demo

log = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationDto])
def list_conversations_endpoint(
    user: Annotated[User | None, Depends(get_current_user)],
) -> list[ConversationDto]:
    """Return all conversations owned by the authenticated user, newest first.

    Each entry includes the first user message in ``messages`` so callers can
    derive a preview snippet without a separate fetch.

    Args:
        user: Authenticated user. Anonymous callers receive 401.

    Returns:
        List of ``ConversationDto`` ordered by creation time descending.

    Raises:
        HTTPException(401): If the request is anonymous.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    rows = list_conversations_for_user(user.id)
    return [
        ConversationDto(
            id=r.id,
            current_cluster_snapshot_id=r.current_cluster_snapshot_id,
            created_at=r.created_at,
            messages=[
                MessageDto(id=m.id, role=m.role, content=m.content, created_at=m.created_at)
                for m in get_messages(r.id)
            ],
        )
        for r in rows
    ]


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation_endpoint(
    conversation_id: uuid.UUID,
    user: Annotated[User | None, Depends(get_current_user)],
) -> None:
    """Delete a conversation owned by the authenticated user.

    Args:
        conversation_id: Conversation UUID to delete.
        user:            Authenticated user. Anonymous callers receive 401.

    Raises:
        HTTPException(401):      If the request is anonymous.
        ConversationNotFound:    If the conversation does not exist.
        NotConversationOwner:    If the authenticated user does not own the conversation.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    row = get_conversation(conversation_id)
    if row is None:
        raise ConversationNotFound(conversation_id)
    if row.user_id != user.id:
        raise NotConversationOwner(conversation_id)
    delete_conversation(conversation_id)
    log.info("conversation_deleted_by_user", extra={"conversation_id": str(conversation_id), "user_id": str(user.id)})


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


@router.patch("/{conversation_id}", response_model=ConversationDto)
def update_conversation_endpoint(
    conversation_id: uuid.UUID,
    body: UpdateConversationRequest,
) -> ConversationDto:
    """Set the active cluster snapshot for a conversation.

    Updates ``current_cluster_snapshot_id`` and records a snapshot ref so the
    conversation_snapshot_refs join table stays consistent.

    Args:
        conversation_id: Conversation UUID.
        body:            Body with the new ``current_cluster_snapshot_id``.

    Returns:
        Updated ``ConversationDto``.

    Raises:
        ConversationNotFound:     If the conversation does not exist.
        ClusterSnapshotNotFound:  If the requested snapshot does not exist.
    """
    row = get_conversation(conversation_id)
    if row is None:
        raise ConversationNotFound(conversation_id)
    if body.current_cluster_snapshot_id is not None:
        snapshot = get_cluster_snapshot(body.current_cluster_snapshot_id)
        if snapshot is None:
            raise ClusterSnapshotNotFound(body.current_cluster_snapshot_id)
        record_conversation_snapshot_ref(conversation_id, body.current_cluster_snapshot_id)
    set_current_cluster_snapshot(conversation_id, body.current_cluster_snapshot_id)
    log.info(
        "active_snapshot_set",
        extra={
            "conversation_id": str(conversation_id),
            "snapshot_id": str(body.current_cluster_snapshot_id) if body.current_cluster_snapshot_id else "null",
        },
    )
    messages = get_messages(conversation_id, limit=20)
    return ConversationDto(
        id=conversation_id,
        current_cluster_snapshot_id=body.current_cluster_snapshot_id,
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

    if _demo.is_replay_mode():
        return await _demo.replay_turn(conversation_id, body.content)

    coordinator = Coordinator()
    result = await coordinator.handle_message(
        conversation_id=conversation_id,
        user_message=body.content,
        conversation_row=row,
    )

    msg_id = append_message(conversation_id, "assistant", result.reply_text, cost_usd=result.turn_cost_usd)
    add_conversation_cost(conversation_id, result.turn_cost_usd)
    log.info("assistant_reply", extra={"conversation_id": str(conversation_id), "cluster_snapshot_id": str(result.cluster_snapshot_id), "turn_cost_usd": result.turn_cost_usd})

    response = SendMessageResponse(
        message=MessageDto(
            id=msg_id,
            role="assistant",
            content=result.reply_text,
            created_at=row.created_at,
            suggestion=result.suggestion,
        ),
        cluster_snapshot_id=result.cluster_snapshot_id,
    )

    if _demo.is_record_mode():
        from backend.routers.dto.cluster_snapshots.build_snapshot import build_snapshot_dto
        snapshot_dto = build_snapshot_dto(result.cluster_snapshot_id)
        _demo.record_turn(str(conversation_id), body.content, response, snapshot_dto)

    return response


@router.get("/{conversation_id}/events")
async def conversation_events(conversation_id: uuid.UUID) -> StreamingResponse:
    """Open a Server-Sent Events stream for real-time turn progress.

    One stream per conversation. The client opens this once on conversation
    load and receives step events for every subsequent turn.

    Args:
        conversation_id: Conversation UUID.

    Returns:
        StreamingResponse of text/event-stream.
    """
    conv_id = str(conversation_id)
    queue = register_queue(conv_id)

    async def _stream():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                event_type = event.get("type", "step")
                data = json.dumps({k: v for k, v in event.items() if k != "type"})
                yield f"event: {event_type}\ndata: {data}\n\n"
        finally:
            unregister_queue(conv_id)

    return StreamingResponse(_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
