import uuid
from dataclasses import dataclass

from backend.agents.intent.types import PartitionSpec
from backend.agents.concept.types import PendingConcept

_awaiting: set[uuid.UUID] = set()
_pending_specs: dict[uuid.UUID, PartitionSpec] = {}
_pending_concepts: dict[uuid.UUID, PendingConcept] = {}


def mark_awaiting(
    conversation_id: uuid.UUID,
    pending_spec: PartitionSpec | None = None,
    pending_concept: PendingConcept | None = None,
) -> None:
    """Flag that the last assistant turn for this conversation was a clarification question.

    Optionally stores a structured ``PartitionSpec`` (numeric bin proposal) or a
    ``PendingConcept`` (concept-axis beeswarm proposal) so that on the next turn the
    coordinator can use the stored data directly rather than relying on the intent
    agent to re-extract it.

    Only one of ``pending_spec`` / ``pending_concept`` should be non-None per call;
    if both are provided, both are stored.

    The flag and any stored data are consumed on the next call to ``take_awaiting``
    and never persisted — both are intentionally ephemeral (lost on server restart).

    Args:
        conversation_id: Conversation UUID to flag.
        pending_spec:    Optional partition spec proposed to the user.
        pending_concept: Optional concept pending user confirmation of cluster count.
    """
    _awaiting.add(conversation_id)
    if pending_spec is not None:
        _pending_specs[conversation_id] = pending_spec
    if pending_concept is not None:
        _pending_concepts[conversation_id] = pending_concept


def take_awaiting(
    conversation_id: uuid.UUID,
) -> tuple[bool, PartitionSpec | None, PendingConcept | None]:
    """
    Return True and clear the flag if this conversation is awaiting a clarification reply.

    Args:
        conversation_id: Conversation UUID to check.

    Returns:
        A tuple of ``(was_awaiting, pending_spec, pending_concept)``.
        - ``was_awaiting`` is ``True`` if the previous turn ended with a clarification question.
        - ``pending_spec`` carries the stored ``PartitionSpec`` when a bin proposal was pending,
          or ``None`` otherwise.
        - ``pending_concept`` carries the stored ``PendingConcept`` when a concept-axis beeswarm
          proposal was pending, or ``None`` otherwise.
    """
    if conversation_id in _awaiting:
        _awaiting.discard(conversation_id)
        spec = _pending_specs.pop(conversation_id, None)
        concept = _pending_concepts.pop(conversation_id, None)
        return True, spec, concept
    return False, None, None
