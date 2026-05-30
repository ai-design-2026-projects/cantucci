import uuid

from backend.agents.intent.types import PartitionSpec
from backend.agents.concept.types import PendingConcept

_awaiting: set[uuid.UUID] = set()
_pending_specs: dict[uuid.UUID, PartitionSpec] = {}
_pending_concepts: dict[uuid.UUID, PendingConcept] = {}
_pending_target_ids: dict[uuid.UUID, uuid.UUID] = {}


def mark_awaiting(
    conversation_id: uuid.UUID,
    pending_spec: PartitionSpec | None = None,
    pending_concept: PendingConcept | None = None,
    target_cluster_id: uuid.UUID | None = None,
) -> None:
    """Flag that the last assistant turn for this conversation was a clarification question.

    Only one of ``pending_spec`` / ``pending_concept`` should be non-None per call;
    if both are provided, both are stored.

    The flag and any stored data are consumed on the next call to ``take_awaiting``
    and never persisted — both are intentionally ephemeral (lost on server restart).

    Args:
        conversation_id:   Conversation UUID to flag.
        pending_spec:      Optional partition spec proposed to the user. When provided,
                           ``take_awaiting`` returns it so the coordinator can bypass
                           LLM bin re-extraction on confirmation.
        pending_concept: Optional concept pending user confirmation of cluster count.
        target_cluster_id: Optional cluster UUID that was the target of the proposed
                           operation. Stored so the coordinator can restore it when the
                           intent agent cannot resolve the reference from a short reply.
    """
    _awaiting.add(conversation_id)
    if pending_spec is not None:
        _pending_specs[conversation_id] = pending_spec
    if pending_concept is not None:
        _pending_concepts[conversation_id] = pending_concept
    if target_cluster_id is not None:
        _pending_target_ids[conversation_id] = target_cluster_id


def is_awaiting(conversation_id: uuid.UUID) -> bool:
    """Return True if this conversation is currently marked as awaiting a clarification reply.

    Unlike ``take_awaiting``, this does not consume the flag.

    Args:
        conversation_id: Conversation UUID to check.

    Returns:
        ``True`` when the conversation is awaiting a reply, ``False`` otherwise.
    """
    return conversation_id in _awaiting

def take_awaiting(
    conversation_id: uuid.UUID,
) -> tuple[bool, PartitionSpec | None, uuid.UUID | None, PendingConcept | None]:
    """
    Return True and clear the flag if this conversation is awaiting a clarification reply.

    Args:
        conversation_id: Conversation UUID to check.

    Returns:
        A tuple of ``(was_awaiting, pending_spec, pending_target_id)``.
        - ``was_awaiting`` is ``True`` if the previous turn ended with a clarification question;
        - ``pending_spec`` carries the stored ``PartitionSpec`` when a bin proposal was pending,
          or ``None`` otherwise
        - ``pending_concept`` carries the stored ``PendingConcept`` when a concept-axis beeswarm
          proposal was pending, or ``None`` otherwise.
        - ``pending_target_id`` carries the cluster UUID that was the target of the pending
          operation, or ``None`` when the target was unknown or not stored.
    """
    if conversation_id in _awaiting:
        _awaiting.discard(conversation_id)
        spec = _pending_specs.pop(conversation_id, None)
        concept = _pending_concepts.pop(conversation_id, None)
        target_id = _pending_target_ids.pop(conversation_id, None)
        return True, spec, target_id, concept
    return False, None, None, None
