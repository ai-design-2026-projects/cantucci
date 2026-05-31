"""Operation recall metric: fraction of GT operations executed during a session."""
import logging
import uuid

from backend.data_access.eval.queries import list_turn_intents
from backend.data_access.eval.types import GroundTruthRow
from eval.types import NAVIGATION_OPERATIONS

log = logging.getLogger(__name__)


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
