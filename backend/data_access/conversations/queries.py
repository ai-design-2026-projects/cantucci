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

    Args:
        user_id:         Owner user UUID, or None for anonymous.
        config_snapshot: Active YAML config dict (stored for replayability).

    Returns:
        UUID of the newly created conversation.
    """
    import json
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO conversations (user_id, config_snapshot)
            VALUES (%s, %s)
            RETURNING id
            """,
            (user_id, json.dumps(config_snapshot)),
        ).fetchone()
    conversation_id: uuid.UUID = row[0]
    log.info("conversation_created", extra={"conversation_id": str(conversation_id)})
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
    return ConversationRow(
        id=row[0],
        user_id=row[1],
        current_cluster_snapshot_id=row[2],
        config_snapshot=row[3],
        created_at=row[4],
    )


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
    return row[0]


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
    result = [
        MessageRow(id=r[0], conversation_id=r[1], role=r[2], content=r[3], created_at=r[4])
        for r in reversed(rows)
    ]
    log.debug("get_messages", extra={"conversation_id": str(conversation_id), "returned": len(result)})
    return result
