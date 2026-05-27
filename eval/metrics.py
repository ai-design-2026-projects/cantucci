"""Deterministic evaluation metrics for a single completed conversation.

All functions read from the database via the data_access layer and return
plain Python values — no LLM calls, no side effects. The caller (runner.py)
is responsible for persisting results via upsert_conversation_metrics.
"""
import logging
import uuid
from dataclasses import dataclass

import numpy as np

from backend.data_access.cluster_snapshots.queries import (
    get_snapshot_member_embeddings,
)
from backend.data_access.conversations.queries import get_conversation, get_messages
from backend.settings import get_settings

log = logging.getLogger(__name__)



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


@dataclass(frozen=True, slots=True)
class ConvergenceResult:
    """Post-hoc convergence detection result.

    Attributes:
        converged:             True if a convergence signal was detected.
        turns_to_convergence:  1-based oracle turn index of the first convergence
                               signal, or None if the conversation did not converge.
        num_turns:             Total number of oracle (user) turns in the conversation.
    """
    converged: bool
    turns_to_convergence: int | None
    num_turns: int


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
    noise_thresh = cfg.eval.noise_prob_threshold
    silhouette_metric = cfg.eval.silhouette_metric

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


def compute_convergence(conversation_id: uuid.UUID) -> ConvergenceResult:
    """Detect convergence from the oracle eval-session status.

    Convergence is meaningful only for simulated oracle sessions: the oracle
    explicitly signals acceptance via intent="accept", which the runner records
    as ``eval_session.status = "converged"``. Real users simply quit — they
    produce no convergence signal and always return ``converged=False``.

    Args:
        conversation_id: UUID of the conversation to check.

    Returns:
        ``ConvergenceResult`` with convergence flag and turn index.
    """
    from backend.data_access.evaluation.queries import get_eval_session_by_conversation

    messages = get_messages(conversation_id, limit=1000)
    num_turns = sum(1 for m in messages if m.role == "user")

    session = get_eval_session_by_conversation(conversation_id)
    if session is not None and session.status == "converged":
        log.debug(
            "convergence_oracle_accept",
            extra={"conversation_id": str(conversation_id), "num_turns": num_turns},
        )
        return ConvergenceResult(converged=True, turns_to_convergence=num_turns, num_turns=num_turns)

    return ConvergenceResult(converged=False, turns_to_convergence=None, num_turns=num_turns)


def compute_cost(conversation_id: uuid.UUID) -> float:
    """Return the accumulated LLM cost for a conversation in USD.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        Total cost in USD, or 0.0 if the conversation row is not found.
    """
    row = get_conversation(conversation_id)
    return row.accumulated_cost_usd if row is not None else 0.0


def compute_spec_satisfaction(
    final_snapshot_id: uuid.UUID,
    spec: dict,
    target_movie_ids: list[int],
) -> float | None:
    """Compute the hidden-spec satisfaction rate for the final clustering.

    Scans the movies in the final snapshot and counts how many are in
    ``target_movie_ids`` (the hidden expanded film set). Returns the fraction
    of final-snapshot movies that appear in the target set. Returns ``None``
    when target_movie_ids is empty.

    Args:
        final_snapshot_id: UUID of the final cluster snapshot.
        spec:              Hidden spec dict (reserved for future richer matching).
        target_movie_ids:  Hidden expanded film set from the ground truth.

    Returns:
        Spec-satisfaction rate in [0, 1], or ``None`` if no ground truth.
    """
    if not target_movie_ids:
        return None

    members = get_snapshot_member_embeddings(final_snapshot_id)
    if not members:
        return 0.0

    target_set = set(target_movie_ids)
    hits = sum(1 for m in members if m.movie_id in target_set)
    rate = hits / len(members)
    log.debug(
        "spec_satisfaction_computed",
        extra={
            "snapshot_id": str(final_snapshot_id),
            "hits": hits,
            "total": len(members),
            "rate": rate,
        },
    )
    return rate
