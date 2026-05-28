import uuid

from backend.agents.clustering.types import PartitionSpec

_awaiting: set[uuid.UUID] = set()
_pending_specs: dict[uuid.UUID, PartitionSpec] = {}


def mark_awaiting(conversation_id: uuid.UUID, pending_spec: PartitionSpec | None = None) -> None:
    """Flag that the last assistant turn for this conversation was a clarification question.

    Optionally stores a structured ``PartitionSpec`` so that on the next turn the
    coordinator can use the proposed bins directly rather than relying on the intent
    agent to re-extract them from the proposal text.

    The flag and any stored spec are consumed on the next call to ``take_awaiting``
    and never persisted — both are intentionally ephemeral (lost on server restart).

    Args:
        conversation_id: Conversation UUID to flag.
        pending_spec:    Optional partition spec proposed to the user. When provided,
                         ``take_awaiting`` returns it so the coordinator can bypass
                         LLM bin re-extraction on confirmation.
    """
    _awaiting.add(conversation_id)
    if pending_spec is not None:
        _pending_specs[conversation_id] = pending_spec


def take_awaiting(conversation_id: uuid.UUID) -> tuple[bool, PartitionSpec | None]:
    """Return True and clear the flag if this conversation is awaiting a clarification reply.

    One-shot: each call either returns ``(True, spec_or_None)`` (and removes both
    entries) or ``(False, None)``.

    Args:
        conversation_id: Conversation UUID to check.

    Returns:
        A tuple of ``(was_awaiting, pending_spec)``.  ``was_awaiting`` is ``True``
        if the previous turn ended with a clarification question; ``pending_spec``
        carries the stored ``PartitionSpec`` when a bin proposal was pending, or
        ``None`` otherwise.
    """
    if conversation_id in _awaiting:
        _awaiting.discard(conversation_id)
        spec = _pending_specs.pop(conversation_id, None)
        return True, spec
    return False, None
