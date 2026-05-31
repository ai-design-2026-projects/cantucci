"""Clarifier trigger rate metric: fraction of turns where the clarifier gate fired."""
import uuid

from backend.data_access.eval.queries import list_turn_intents


def compute_clarifier_trigger_rate(conversation_id: uuid.UUID) -> float:
    """Compute the fraction of turns on which the clarifier gate fired.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Rate in [0, 1]. Returns ``0.0`` when there are no recorded turn_intents.
    """
    turn_intents = list_turn_intents(conversation_id)
    if not turn_intents:
        return 0.0

    turns_with_clarifier = {ti.turn_number for ti in turn_intents if ti.clarifier_fired}
    all_turns = {ti.turn_number for ti in turn_intents}
    return len(turns_with_clarifier) / len(all_turns)
