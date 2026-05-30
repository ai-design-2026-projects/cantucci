"""Deterministic evaluation metrics for a single completed conversation.

All functions read from the database via the data_access layer and return
plain Python values — no LLM calls, no side effects. The caller (runner.py)
is responsible for persisting results via upsert_conversation_metrics.
"""
import logging
import uuid
from dataclasses import dataclass

import numpy as np

from backend.data_access.cluster_snapshots.queries import get_snapshot_member_embeddings
from backend.data_access.conversations.queries import get_conversation, get_messages
from backend.data_access.eval.queries import list_turn_intents
from backend.data_access.eval.types import GroundTruthRow
from backend.settings import get_settings
from eval.config import load_eval_harness_config

log = logging.getLogger(__name__)

_GT_OPERATION_VOCABULARY = {"cluster", "merge", "focus", "cross_filter"}
_NAVIGATION_MODES = {"cluster", "merge", "focus", "cross_filter"}


@dataclass(frozen=True, slots=True)
class ClusteringMetrics:
    """Deterministic clustering-quality metrics from the final snapshot.

    Attributes:
        silhouette:           Silhouette score in [-1, 1], or None if not computable.
        mean_membership_prob: Mean argmax membership probability across all movies.
        noise_fraction:       Fraction of movies below the noise_prob_threshold.
        final_num_clusters:   Number of clusters in the snapshot.
    """
    silhouette: float | None
    mean_membership_prob: float | None
    noise_fraction: float | None
    final_num_clusters: int


def compute_clustering_metrics(snapshot_id: uuid.UUID) -> ClusteringMetrics:
    """Compute silhouette score and membership statistics for a cluster snapshot.

    Fuses text and review embeddings with the active config weights, assigns
    each movie to its argmax cluster, and runs silhouette_score. Silhouette is
    None when there are fewer than 2 clusters or any cluster has fewer than
    2 members (sklearn requirement).

    Args:
        snapshot_id: UUID of the cluster snapshot to evaluate.

    Returns:
        ``ClusteringMetrics`` with silhouette and summary statistics.
    """
    from sklearn.metrics import silhouette_score

    cfg = get_settings()
    harness_cfg = load_eval_harness_config()
    noise_thresh = harness_cfg.scorer.noise_prob_threshold
    silhouette_metric = harness_cfg.scorer.silhouette_metric

    members = get_snapshot_member_embeddings(snapshot_id)
    if not members:
        return ClusteringMetrics(
            silhouette=None,
            mean_membership_prob=None,
            noise_fraction=None,
            final_num_clusters=0,
        )

    cluster_ids = sorted({m.cluster_id for m in members})
    num_clusters = len(cluster_ids)
    label_map = {cid: i for i, cid in enumerate(cluster_ids)}

    text_weight = cfg.fusion.runtime_weights.get("text", 0.6)
    review_weight = cfg.fusion.runtime_weights.get("review", 0.4)
    total = text_weight + review_weight if (text_weight + review_weight) > 0 else 1.0
    text_w = text_weight / total
    review_w = review_weight / total

    embeddings: list[np.ndarray] = []
    labels: list[int] = []

    for m in members:
        if m.text_embedding is None:
            continue
        text_arr = np.array(m.text_embedding, dtype=np.float32)
        if m.review_embedding is not None:
            review_arr = np.array(m.review_embedding, dtype=np.float32)
            fused = text_w * text_arr + review_w * review_arr
        else:
            fused = text_arr
        norm = np.linalg.norm(fused)
        if norm > 0:
            fused = fused / norm
        embeddings.append(fused)
        labels.append(label_map[m.cluster_id])

    if not embeddings:
        return ClusteringMetrics(
            silhouette=None,
            mean_membership_prob=None,
            noise_fraction=None,
            final_num_clusters=num_clusters,
        )

    embedding_matrix = np.stack(embeddings)
    label_array = np.array(labels)
    unique_labels = np.unique(label_array)

    silhouette: float | None = None
    if len(unique_labels) >= 2 and all(
        np.sum(label_array == lbl) >= 2 for lbl in unique_labels
    ):
        try:
            silhouette = float(silhouette_score(embedding_matrix, label_array, metric=silhouette_metric))
        except Exception:
            log.warning("silhouette_score_failed", exc_info=True)

    mean_prob: float | None = None
    noise_frac: float | None = None
    if members:
        probs = [m.probability for m in members]
        mean_prob = float(np.mean(probs))
        noise_frac = float(sum(1 for p in probs if p < noise_thresh) / len(probs))

    log.debug(
        "clustering_metrics_computed",
        extra={
            "snapshot_id": str(snapshot_id),
            "num_clusters": num_clusters,
            "silhouette": silhouette,
            "n_movies": len(embeddings),
        },
    )
    return ClusteringMetrics(
        silhouette=silhouette,
        mean_membership_prob=mean_prob,
        noise_fraction=noise_frac,
        final_num_clusters=num_clusters,
    )


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
