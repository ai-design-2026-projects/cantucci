"""Turn-count metric: number of oracle (user) turns in a conversation."""
import uuid

from backend.data_access.conversations.queries import get_messages


def compute_num_turns(conversation_id: uuid.UUID) -> int:
    """Return the number of oracle (user) turns in the conversation.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Count of messages with role ``"user"``.
    """
    messages = get_messages(conversation_id, limit=1000)
    return sum(1 for m in messages if m.role == "user")
