import asyncio
import json
import logging
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.coordinator.agent import Coordinator
from backend.coordinator.types import sentinel_cluster_snapshot_id
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
    get_conversation_cluster_snapshots,
    record_conversation_snapshot_ref,
)
from backend.exceptions import ClusterSnapshotNotFound, ConversationNotFound, NotConversationOwner
from backend.coordinator.tools.progress import register_queue, unregister_queue
from backend.routers.auth_deps import get_current_user
from backend.routers.dto.conversations.dtos import (
    ConversationDto,
    MessageDto,
    SendMessageRequest,
    SendMessageResponse,
    UpdateConversationRequest,
)
from backend.routers.dto.cluster_snapshots.dtos import ClusterSnapshotGraphDto
from backend.routers.dto.cluster_snapshots.build_snapshot import build_snapshot_graph_dto
from backend.settings import get_config_snapshot
import demo.utils.replay as _demo
import demo.utils.record as _demo_record

log = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/get_history", response_model=list[ConversationDto])
def list_conversations_endpoint(
    user: Annotated[User | None, Depends(get_current_user)],
) -> list[ConversationDto]:
    """Return all conversations owned by the authenticated user, ordered newest first.

    Each entry includes all messages so callers can render a preview snippet
    without issuing a second request.

    Args:
        user: Authenticated user injected by the auth dependency.

    Returns:
        List of ``ConversationDto`` ordered by creation time descending.

    Raises:
        HTTPException(401): If the caller is not authenticated.
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
                MessageDto(
                    id=m.id, role=m.role, content=m.content, created_at=m.created_at,
                    suggestion=m.suggestion, axis_concept_id=m.axis_concept_id,
                )
                for m in get_messages(r.id)
            ],
        )
        for r in rows
    ]


@router.post("/create", response_model=ConversationDto, status_code=201)
async def create_new_conversation(
    user: Annotated[User | None, Depends(get_current_user)],
) -> ConversationDto:
    """Create a new conversation and return it with an empty messages list.

    The conversation starts with no active cluster snapshot; the first assistant
    reply will produce the root cluster snapshot from the base HDBSCAN clustering.
    Both authenticated and anonymous users may create conversations.

    Args:
        user: Authenticated user, or None for anonymous callers.

    Returns:
        ``ConversationDto`` with an empty messages list and no cluster snapshot.
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


@router.get("/get/{conversation_id}", response_model=ConversationDto)
def get_conversation_endpoint(conversation_id: uuid.UUID) -> ConversationDto:
    """Return a conversation with its 20 most recent messages.

    Args:
        conversation_id: Conversation UUID.

    Returns:
        ``ConversationDto`` with up to 20 most recent messages and the active
        cluster snapshot ID.

    Raises:
        ConversationNotFound: If no conversation with this ID exists.
    """
    row = get_conversation(conversation_id)
    if row is None:
        raise ConversationNotFound(conversation_id)
    messages = get_messages(conversation_id, limit=20)
    return ConversationDto(
        id=row.id,
        current_cluster_snapshot_id=row.current_cluster_snapshot_id,
        messages=[
            MessageDto(
                id=m.id, role=m.role, content=m.content, created_at=m.created_at,
                suggestion=m.suggestion, axis_concept_id=m.axis_concept_id,
            )
            for m in messages
        ],
        created_at=row.created_at,
    )


@router.delete("/delete/{conversation_id}", status_code=204)
def delete_conversation_endpoint(
    conversation_id: uuid.UUID,
    user: Annotated[User | None, Depends(get_current_user)],
) -> None:
    """Delete a conversation owned by the authenticated user.

    Only the owning user may delete their conversation. The operation is
    permanent and cascades to all associated messages.

    Args:
        conversation_id: Conversation UUID to delete.
        user:            Authenticated user injected by the auth dependency.

    Raises:
        HTTPException(401):   If the caller is not authenticated.
        ConversationNotFound: If no conversation with this ID exists.
        NotConversationOwner: If the caller does not own this conversation.
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


@router.patch("/update_snapshot/{conversation_id}", response_model=ConversationDto)
def update_conversation_endpoint(
    conversation_id: uuid.UUID,
    body: UpdateConversationRequest,
) -> ConversationDto:
    """Set the active cluster snapshot for a conversation.

    Updates ``current_cluster_snapshot_id`` and records a row in
    ``conversation_snapshot_refs`` so the join table stays consistent.
    Pass ``null`` to detach the conversation from any snapshot.

    Args:
        conversation_id: Conversation UUID.
        body:            ``UpdateConversationRequest`` with the new snapshot ID (or null).

    Returns:
        Updated ``ConversationDto`` with the new active snapshot and recent messages.

    Raises:
        ConversationNotFound:    If no conversation with this ID exists.
        ClusterSnapshotNotFound: If the requested snapshot does not exist.
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
            MessageDto(
                id=m.id, role=m.role, content=m.content, created_at=m.created_at,
                suggestion=m.suggestion, axis_concept_id=m.axis_concept_id,
            )
            for m in messages
        ],
        created_at=row.created_at,
    )


@router.post("/send_message/{conversation_id}", response_model=SendMessageResponse)
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    user: Annotated[User | None, Depends(get_current_user)],
) -> SendMessageResponse:
    """Submit a user message and receive the assistant reply with an updated cluster snapshot.

    The coordinator runs intent detection, clustering, clarification, and reply
    generation. On success the assistant message and the new cluster snapshot ID
    are returned together so the frontend can update both panels atomically.

    Args:
        conversation_id: Conversation UUID.
        body:            ``SendMessageRequest`` containing the user message text.
        user:            Authenticated user, or None for anonymous callers.

    Returns:
        ``SendMessageResponse`` with the assistant ``MessageDto`` and the new
        cluster snapshot ID (null if the snapshot was not updated this turn).

    Raises:
        ConversationNotFound: If no conversation with this ID exists.
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

    msg_id = append_message(
        conversation_id,
        "assistant",
        result.reply_text,
        cost_usd=result.turn_cost_usd,
        suggestion=result.suggestion,
        axis_concept_id=result.axis_concept_id,
    )
    add_conversation_cost(conversation_id, result.turn_cost_usd)

    response_cluster_snapshot_id = (
        None
        if result.cluster_snapshot_id == sentinel_cluster_snapshot_id()
        else result.cluster_snapshot_id
    )
    log.info("assistant_reply", extra={"conversation_id": str(conversation_id), "cluster_snapshot_id": str(result.cluster_snapshot_id), "turn_cost_usd": result.turn_cost_usd})

    response = SendMessageResponse(
        message=MessageDto(
            id=msg_id,
            role="assistant",
            content=result.reply_text,
            created_at=row.created_at,
            suggestion=result.suggestion,
            axis_concept_id=result.axis_concept_id,
        ),
        cluster_snapshot_id=response_cluster_snapshot_id,
    )

    if _demo_record.is_record_mode() and response_cluster_snapshot_id is not None:
        from backend.routers.dto.cluster_snapshots.build_snapshot import build_snapshot_dto
        snapshot_dto = build_snapshot_dto(response_cluster_snapshot_id)
        _demo_record.record_turn(str(conversation_id), body.content, response, snapshot_dto)

    return response


@router.get("/progress_stream/{conversation_id}")
async def conversation_events(conversation_id: uuid.UUID) -> StreamingResponse:
    """Open a Server-Sent Events stream for real-time turn progress updates.

    One stream per conversation. The client opens this connection once on page
    load and receives step events (intent, clustering, clarification, reply) for
    every subsequent turn. A heartbeat comment is emitted every 15 seconds to
    keep the connection alive through proxies.

    Args:
        conversation_id: Conversation UUID.

    Returns:
        ``StreamingResponse`` of ``text/event-stream``.
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


@router.get("/get_cluster_snapshot/{conversation_id}", response_model=ClusterSnapshotGraphDto)
def get_cluster_snapshot_graph(conversation_id: uuid.UUID) -> ClusterSnapshotGraphDto:
    """Return all cluster snapshot nodes for a conversation as a directed acyclic graph.

    Each node carries id, parent_id, operation, and created_at — enough to render
    an evolution-map force graph without loading full cluster membership data.
    The root snapshot (no parent) is always present if any clustering has occurred.

    Args:
        conversation_id: Conversation UUID.

    Returns:
        ``ClusterSnapshotGraphDto`` with all snapshot nodes for this conversation.
    """
    if _demo.is_replay_mode():
        recorded = _demo.get_recorded_snapshot_graph(str(conversation_id))
        if recorded is not None:
            return recorded

    snapshots = get_conversation_cluster_snapshots(conversation_id)
    dto = build_snapshot_graph_dto(snapshots)
    log.debug("cluster_snapshot_graph", extra={"conversation_id": str(conversation_id), "n_nodes": len(dto.cluster_snapshots)})
    return dto
