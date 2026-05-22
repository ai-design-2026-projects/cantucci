import logging
import uuid
from typing import Any

from backend.data_access.connection import transaction
from backend.data_access.conversations.types import ConversationRow, MessageRow

log = logging.getLogger(__name__)


def create_conversation(
    user_id: uuid.UUID | None,
    config_snapshot: dict[str, Any],
) -> uuid.UUID:
    """Insert a new conversation row and return its UUID.

    If a global root cluster snapshot exists, the new conversation's
    ``current_cluster_snapshot_id`` is pre-seeded to point at it and a
    reference is recorded in ``conversation_snapshot_refs``.

    Args:
        user_id:         Owner user UUID, or None for anonymous.
        config_snapshot: Active YAML config dict (stored for replayability).

    Returns:
        UUID of the newly created conversation.
    """
    import json

    from backend.data_access.cluster_snapshots.queries import (
        get_root_cluster_snapshot,
        record_conversation_snapshot_ref,
    )

    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO conversations (user_id, config_snapshot)
            VALUES (%s, %s)
            RETURNING id
            """,
            (user_id, json.dumps(config_snapshot)),
        ).fetchone()
    conversation_id: uuid.UUID = row["id"]

    root = get_root_cluster_snapshot()
    if root is not None:
        set_current_cluster_snapshot(conversation_id, root.id)
        record_conversation_snapshot_ref(conversation_id, root.id)

    log.info(
        "conversation_created",
        extra={
            "conversation_id": str(conversation_id),
            "seeded_root_snapshot_id": str(root.id) if root else None,
        },
    )
    return conversation_id


def get_conversation(conversation_id: uuid.UUID) -> ConversationRow | None:
    """Fetch a single conversation row by ID.

    Args:
        conversation_id: UUID to look up.

    Returns:
        ``ConversationRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, user_id, current_cluster_snapshot_id, config_snapshot, created_at FROM conversations WHERE id = %s",
            (conversation_id,),
        ).fetchone()
    if row is None:
        return None
    return ConversationRow.from_row(row)


def set_current_cluster_snapshot(conversation_id: uuid.UUID, cluster_snapshot_id: uuid.UUID) -> None:
    """Update the current_cluster_snapshot_id pointer for a conversation.

    Args:
        conversation_id:     Conversation to update.
        cluster_snapshot_id: New current cluster snapshot UUID.
    """
    with transaction() as conn:
        conn.execute(
            "UPDATE conversations SET current_cluster_snapshot_id = %s WHERE id = %s",
            (cluster_snapshot_id, conversation_id),
        )
    log.debug("current_cluster_snapshot_set", extra={"conversation_id": str(conversation_id), "cluster_snapshot_id": str(cluster_snapshot_id)})


def append_message(
    conversation_id: uuid.UUID,
    role: str,
    content: str,
) -> uuid.UUID:
    """Insert a message row and return its UUID.

    Args:
        conversation_id: Parent conversation.
        role:            ``"user"`` or ``"assistant"``.
        content:         Message text.

    Returns:
        UUID of the newly inserted message.
    """
    with transaction() as conn:
        row = conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s) RETURNING id",
            (conversation_id, role, content),
        ).fetchone()
    return row["id"]


def get_messages(conversation_id: uuid.UUID, limit: int = 20) -> list[MessageRow]:
    """Return the most recent *limit* messages for a conversation, oldest first.

    Args:
        conversation_id: Parent conversation UUID.
        limit:           Maximum number of messages to return.

    Returns:
        List of ``MessageRow`` ordered by creation time ascending.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, conversation_id, role, content, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (conversation_id, limit),
        ).fetchall()
    result = [MessageRow.from_row(r) for r in reversed(rows)]
    log.debug("get_messages", extra={"conversation_id": str(conversation_id), "returned": len(result)})
    return result
