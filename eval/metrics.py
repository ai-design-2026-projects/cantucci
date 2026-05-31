"""Deterministic evaluation metrics for a single completed conversation.

All functions read from the database via the data_access layer and return
plain Python values — no LLM calls, no side effects. The caller (runner.py)
is responsible for persisting results via upsert_conversation_metrics.
"""
import logging
import uuid
from dataclasses import dataclass

from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.conversations.queries import get_conversation, get_messages
from backend.data_access.eval.queries import list_turn_intents
from backend.data_access.eval.types import GroundTruthRow

log = logging.getLogger(__name__)

_GT_OPERATION_VOCABULARY = {"cluster", "merge", "focus", "cross_filter"}
_NAVIGATION_MODES = {"cluster", "merge", "focus", "cross_filter"}


@dataclass(frozen=True, slots=True)
class ClusteringMetrics:
    """Cluster-count metric from the final snapshot.

    Attributes:
        final_num_clusters: Number of clusters in the snapshot.
    """
    final_num_clusters: int


def compute_clustering_metrics(snapshot_id: uuid.UUID) -> ClusteringMetrics:
    """Return the number of clusters in the given snapshot.

    Reads the cluster snapshot via ``get_cluster_snapshot_with_clusters``.

    Args:
        snapshot_id: UUID of the cluster snapshot to evaluate.

    Returns:
        ``ClusteringMetrics`` with the final cluster count.
    """
    snapshot_with_clusters = get_cluster_snapshot_with_clusters(snapshot_id)
    if snapshot_with_clusters is None:
        return ClusteringMetrics(final_num_clusters=0)
    num_clusters = len(snapshot_with_clusters.clusters)
    log.debug(
        "clustering_metrics_computed",
        extra={"snapshot_id": str(snapshot_id), "num_clusters": num_clusters},
    )
    return ClusteringMetrics(final_num_clusters=num_clusters)


def compute_cost(conversation_id: uuid.UUID) -> float:
    """Return the accumulated LLM cost for a conversation in USD.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Total cost in USD, or 0.0 if the conversation row is not found.
    """
    row = get_conversation(conversation_id)
    return row.accumulated_cost_usd if row is not None else 0.0


def compute_num_operations(conversation_id: uuid.UUID) -> int:
    """Count turn_intents rows whose mode is a NavigationMode value.

    Counts all four NavigationMode values (cluster, merge, focus, cross_filter).

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Total number of navigation operation intents recorded.
    """
    turn_intents = list_turn_intents(conversation_id)
    return sum(1 for ti in turn_intents if ti.mode in _NAVIGATION_MODES)


def compute_clarifier_trigger_rate(conversation_id: uuid.UUID) -> float:
    """Compute the fraction of turns on which the clarifier fired.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Rate in [0, 1]. Returns 0.0 when there are no recorded turn_intents.
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

    Matches executed (op, concept) pairs against the GT operations list.
    Op-type match is exact; concept match is case-insensitive after stripping
    whitespace. Only the four GT-vocabulary ops are counted (cluster, merge,
    focus, cross_filter).

    Args:
        conversation_id: UUID of the conversation.
        ground_truth:    Ground truth row. Returns None when absent.

    Returns:
        Fraction of GT ``(op, concept)`` pairs found in turn_intents,
        or None if no ground truth is provided or GT has no operations.
    """
    if ground_truth is None:
        return None

    gt_ops = [
        (op["op"], op["concept"].strip().lower())
        for op in ground_truth.operations
        if op["op"] in _GT_OPERATION_VOCABULARY
    ]
    if not gt_ops:
        return None

    turn_intents = list_turn_intents(conversation_id)
    executed = {
        (ti.mode, (ti.concept or "").strip().lower())
        for ti in turn_intents
        if ti.mode in _GT_OPERATION_VOCABULARY
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


def compute_num_turns(conversation_id: uuid.UUID) -> int:
    """Return the number of user (oracle) turns in the conversation.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Count of messages with role "user".
    """
    messages = get_messages(conversation_id, limit=1000)
    return sum(1 for m in messages if m.role == "user")
