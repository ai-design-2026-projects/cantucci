"""Accumulated LLM cost metric for a completed conversation."""
import uuid

from backend.data_access.conversations.queries import get_conversation


def compute_cost(conversation_id: uuid.UUID) -> float:
    """Return the accumulated LLM cost for a conversation in USD.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Total cost in USD; ``0.0`` when the conversation row is not found.
    """
    row = get_conversation(conversation_id)
    return row.accumulated_cost_usd if row is not None else 0.0
