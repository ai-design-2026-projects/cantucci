"""Conversation-level deterministic metrics for the evaluation harness."""
import logging
import uuid

from backend.data_access.conversations.queries import get_conversation, get_messages
from backend.data_access.eval.queries import list_turn_intents
from backend.data_access.eval.types import GroundTruthRow
from eval.types import NAVIGATION_OPERATIONS

log = logging.getLogger(__name__)


def compute_cost(conversation_id: uuid.UUID) -> float:
    """Return the accumulated LLM cost for a conversation in USD.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Total cost in USD; ``0.0`` when the conversation row is not found.
    """
    row = get_conversation(conversation_id)
    return row.accumulated_cost_usd if row is not None else 0.0


def compute_num_turns(conversation_id: uuid.UUID) -> int:
    """Return the number of oracle (user) turns in the conversation.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Count of messages with role ``"user"``.
    """
    messages = get_messages(conversation_id, limit=1000)
    return sum(1 for m in messages if m.role == "user")


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


def compute_operation_recall(
    conversation_id: uuid.UUID,
    ground_truth: GroundTruthRow | None,
) -> float | None:
    """Compute operation recall against a ground truth trajectory.

    Matches executed ``(op, concept)`` pairs against the GT operations list.
    Op-type match is exact; concept match is case-insensitive after stripping
    whitespace. Only navigation ops (``NAVIGATION_OPERATIONS``) are counted.

    Args:
        conversation_id: UUID of the conversation.
        ground_truth:    Ground truth row. Returns ``None`` when absent.

    Returns:
        Fraction of GT ``(op, concept)`` pairs found in turn_intents,
        or ``None`` if no ground truth or GT has no navigation operations.
    """
    if ground_truth is None:
        return None

    gt_ops = [
        (op["op"], op["concept"].strip().lower())
        for op in ground_truth.operations
        if op["op"] in NAVIGATION_OPERATIONS
    ]
    if not gt_ops:
        return None

    turn_intents = list_turn_intents(conversation_id)
    executed = {
        (ti.mode, (ti.concept or "").strip().lower())
        for ti in turn_intents
        if ti.mode in NAVIGATION_OPERATIONS
    }

    matched = sum(1 for pair in gt_ops if pair in executed)
    recall = matched / len(gt_ops)

    log.debug(
        "operation_recall_computed",
        extra={
            "conversation_id": str(conversation_id),
            "gt_ops": len(gt_ops),
            "matched": matched,
            "recall": recall,
        },
    )
    return recall
