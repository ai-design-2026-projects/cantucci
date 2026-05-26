import uuid

_awaiting: set[uuid.UUID] = set()


def mark_awaiting(conversation_id: uuid.UUID) -> None:
    """Flag that the last assistant turn for this conversation was a clarification question.

    The flag is consumed on the next call to ``take_awaiting`` and never persisted —
    it is intentionally ephemeral (lost on server restart).

    Args:
        conversation_id: Conversation UUID to flag.
    """
    _awaiting.add(conversation_id)


def take_awaiting(conversation_id: uuid.UUID) -> bool:
    """Return True and clear the flag if this conversation is awaiting a clarification reply.

    One-shot: each call either returns True (and removes the entry) or False.

    Args:
        conversation_id: Conversation UUID to check.

    Returns:
        ``True`` if the previous turn ended with a clarification question, ``False`` otherwise.
    """
    if conversation_id in _awaiting:
        _awaiting.discard(conversation_id)
        return True
    return False
