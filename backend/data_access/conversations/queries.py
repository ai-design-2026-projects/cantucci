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

    New conversations start in the unclustered state (``current_cluster_snapshot_id``
    is NULL). The first ``go_to_base`` action by the user activates the pre-computed
    root snapshot and records the snapshot ref.

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
    conversation_id: uuid.UUID = row["id"]

    log.info(
        "conversation_created",
        extra={"conversation_id": str(conversation_id)},
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
            "SELECT id, user_id, current_cluster_snapshot_id, config_snapshot, created_at, accumulated_cost_usd FROM conversations WHERE id = %s",
            (conversation_id,),
        ).fetchone()
    if row is None:
        return None
    return ConversationRow.from_row(row)


def set_current_cluster_snapshot(conversation_id: uuid.UUID, cluster_snapshot_id: uuid.UUID | None) -> None:
    """Update the current_cluster_snapshot_id pointer for a conversation.

    Pass ``None`` to move the conversation into the unclustered state (RESET).

    Args:
        conversation_id:     Conversation to update.
        cluster_snapshot_id: New current cluster snapshot UUID, or ``None`` to unset.
    """
    with transaction() as conn:
        conn.execute(
            "UPDATE conversations SET current_cluster_snapshot_id = %s WHERE id = %s",
            (cluster_snapshot_id, conversation_id),
        )
    log.debug(
        "current_cluster_snapshot_set",
        extra={
            "conversation_id": str(conversation_id),
            "cluster_snapshot_id": str(cluster_snapshot_id) if cluster_snapshot_id else "null",
        },
    )


def append_message(
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    cost_usd: float = 0.0,
    suggestion: str | None = None,
    axis_concept_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a message row and return its UUID.

    Args:
        conversation_id: Parent conversation.
        role:            ``"user"`` or ``"assistant"``.
        content:         Message text.
        cost_usd:        LLM cost for this turn in USD. Pass 0 for user messages.
        suggestion:      Optional follow-up suggestion text from the suggester agent.
        axis_concept_id: UUID of the concept backing a beeswarm axis-distribution proposal.

    Returns:
        UUID of the newly inserted message.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, cost_usd, suggestion, axis_concept_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (conversation_id, role, content, cost_usd, suggestion, axis_concept_id),
        ).fetchone()
    return row["id"]


def add_conversation_cost(conversation_id: uuid.UUID, delta_usd: float) -> None:
    """Atomically increment the accumulated_cost_usd for a conversation.

    Args:
        conversation_id: Conversation to update.
        delta_usd:       Additional cost in USD to add to the running total.
    """
    with transaction() as conn:
        conn.execute(
            "UPDATE conversations SET accumulated_cost_usd = accumulated_cost_usd + %s WHERE id = %s",
            (delta_usd, conversation_id),
        )
    log.debug("conversation_cost_updated", extra={"conversation_id": str(conversation_id), "delta_usd": delta_usd})


def list_conversations_for_user(user_id: uuid.UUID) -> list[ConversationRow]:
    """Return all conversations owned by *user_id*, newest first.

    Args:
        user_id: Owner user UUID.

    Returns:
        List of ``ConversationRow`` ordered by ``created_at`` descending.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, current_cluster_snapshot_id, config_snapshot, created_at, accumulated_cost_usd
            FROM conversations
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    result = [ConversationRow.from_row(r) for r in rows]
    log.debug("list_conversations_for_user", extra={"user_id": str(user_id), "returned": len(result)})
    return result



def delete_conversation(conversation_id: uuid.UUID) -> None:
    """Hard-delete a conversation and its cascade dependents.

    Cascade FK constraints remove ``messages`` and ``conversation_snapshot_refs``
    rows automatically (defined in migrations 005 and 009).

    Args:
        conversation_id: Conversation UUID to delete.
    """
    with transaction() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE id = %s",
            (conversation_id,),
        )
    log.info("conversation_deleted", extra={"conversation_id": str(conversation_id)})


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
            SELECT id, conversation_id, role, content, created_at, cost_usd, suggestion, axis_concept_id
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
