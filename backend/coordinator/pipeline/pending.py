import dataclasses
import uuid

from backend.agents.concept.types import PendingConcept
from backend.agents.intent.types import IntentAction, NavigationMode, PartitionSpec
from backend.coordinator.tools.clarification_state import take_awaiting
from backend.data_access.conversations.queries import get_messages


def resolve_clarification_context(
    conversation_id: uuid.UUID,
) -> tuple[bool, str | None, PartitionSpec | None, uuid.UUID | None, PendingConcept | None]:
    """Check for a pending clarification and fetch the prior question text if set.

    Consumes the in-memory awaiting flag via ``take_awaiting``; subsequent
    calls on the same turn will see ``was_awaiting=False``.

    Args:
        conversation_id: Conversation UUID to check.

    Returns:
        Tuple of (was_awaiting, clarification_question, pending_spec, pending_target_id, pending_concept).
        ``clarification_question`` is the prior assistant message text when
        ``was_awaiting`` is True, else ``None``.
        ``pending_target_id`` is the cluster UUID stored from the prior turn when
        a bin proposal was made for a specific cluster, else ``None``.
    """
    # Check if we're awaiting clarification on a previous message
    was_awaiting, pending_spec, pending_target_id, pending_concept = take_awaiting(conversation_id)
    clarification_question: str | None = None
    # If so, find the most recent assistant message to use as the clarification question for intent classification.
    if was_awaiting:
        recent = get_messages(conversation_id, limit=2)
        prior_assistant = next((m for m in reversed(recent) if m.role == "assistant"), None)
        if prior_assistant is not None:
            clarification_question = prior_assistant.content
    return was_awaiting, clarification_question, pending_spec, pending_target_id, pending_concept


def apply_pending_spec_override(
    actions: list[IntentAction],
    pending_spec: PartitionSpec,
    pending_target_id: uuid.UUID | None = None,
) -> list[IntentAction]:
    """Patch any CLUSTER action with the spec stored from the clarification turn.

    On a "yes" or short-answer reply the intent agent may re-extract bins,
    attributes, or target cluster incorrectly.  The stored spec and target are
    authoritative for three cases:

    - Bin-proposal confirmation: ``pending_spec.bins is not None`` and the
      returned action has no bins → restore the stored spec wholesale.
    - Target-clarification confirmation: the stored spec has no bins but the
      returned attribute differs → restore just the attribute.
    - Target restoration: ``pending_target_id`` was stored (the original cluster
      the operation targeted) and the intent agent returned ``None`` for
      ``target_cluster_id`` (cannot resolve from a bare "Ok") → restore the ID.

    Args:
        actions:           Classified actions from the intent agent (may be mutated copy).
        pending_spec:      Stored partition spec from the prior clarification turn.
        pending_target_id: Cluster UUID stored when the bin proposal was made for a
                           specific cluster; ``None`` when the target was not known.

    Returns:
        New list of actions with CLUSTER entries patched where needed.
    """
    result = list(actions)
    for i, a in enumerate(result):
        if a.mode == NavigationMode.CLUSTER and a.partition_spec is not None:
            patched = a
            if pending_spec.bins is not None and a.partition_spec.bins is None:
                # Bin-proposal confirmation: stored spec is authoritative regardless of
                # which attribute the intent agent returned on the short "yes" reply.
                patched = dataclasses.replace(patched, partition_spec=pending_spec)
            elif pending_spec.bins is None and a.partition_spec.attribute != pending_spec.attribute:
                # Target-clarification confirmation: intent returned the wrong attribute;
                # restore the one from the stored spec.
                patched = dataclasses.replace(
                    patched,
                    partition_spec=dataclasses.replace(
                        patched.partition_spec, attribute=pending_spec.attribute
                    ),
                )
            if pending_target_id is not None and patched.target_cluster_id is None:
                # The intent agent could not resolve the target cluster from a short reply;
                # restore the ID that was known at the time the proposal was made.
                patched = dataclasses.replace(patched, target_cluster_id=pending_target_id)
            result[i] = patched
    return result


def apply_pending_concept_override(
    actions: list[IntentAction],
    pending_concept: PendingConcept,
) -> list[IntentAction]:
    """Patch the CLUSTER action to reuse the persisted concept scores from the proposal turn.

    When the user is confirming a concept-axis beeswarm proposal (by stating the
    desired cluster count), the intent agent may re-extract the concept name but
    we want to reuse the already-computed and persisted scores rather than calling
    the concept agent again.  If the user redirected to a *different* concept (i.e.
    the returned action has a concept string and it differs from the pending name),
    we skip the override and let the new concept flow through normally.

    Args:
        actions:         Classified actions from the intent agent.
        pending_concept: Stored concept context from the prior proposal turn.

    Returns:
        New list of actions with the CLUSTER entry patched to carry ``reuse_concept_id``
        and the original ``target_cluster_id``.
    """
    result = list(actions)
    for i, a in enumerate(result):
        if a.mode == NavigationMode.CLUSTER:
            if a.concept is not None and a.concept != pending_concept.concept_name:
                break
            result[i] = dataclasses.replace(
                a,
                reuse_concept_id=pending_concept.concept_id,
                target_cluster_id=pending_concept.target_cluster_id,
            )
            break
    return result
