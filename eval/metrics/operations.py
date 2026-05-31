"""Navigation operation count metric for a completed conversation."""
import uuid

from backend.data_access.eval.queries import list_turn_intents
from eval.types import NAVIGATION_OPERATIONS


def compute_num_operations(conversation_id: uuid.UUID) -> int:
    """Count turn_intents rows whose mode is a navigation operation.

    Counts all modes that are in ``NAVIGATION_OPERATIONS``
    (cluster, merge, focus, cross_filter, exclude).

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Total number of navigation operation intents recorded.
    """
    turn_intents = list_turn_intents(conversation_id)
    return sum(1 for ti in turn_intents if ti.mode in NAVIGATION_OPERATIONS)
