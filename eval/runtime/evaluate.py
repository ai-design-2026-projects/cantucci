"""Compute and persist all deterministic metrics and judge scores for a conversation.

This is the offline scoring step — safe to call multiple times (idempotent).
"""
import logging
import uuid

from backend.data_access.conversations.queries import get_conversation
from backend.data_access.eval.queries import (
    get_ground_truth_by_slug,
    insert_judge_score,
    upsert_conversation_metrics,
)
from eval.config import load_eval_harness_config
from eval.judge.agent import judge_conversation
from eval.metrics.clarifier import compute_clarifier_trigger_rate
from eval.metrics.clustering import compute_clustering_metrics
from eval.metrics.cost import compute_cost
from eval.metrics.operations import compute_num_operations
from eval.metrics.recall import compute_operation_recall
from eval.metrics.turns import compute_num_turns

log = logging.getLogger(__name__)


async def evaluate_conversation(
    conversation_id: uuid.UUID,
    ground_truth_slug: str | None = None,
) -> None:
    """Compute and persist all deterministic metrics and judge scores for a conversation.

    Safe to call multiple times — ``upsert_conversation_metrics`` overwrites the
    previous row, and ``insert_judge_score`` is guarded by a unique constraint on
    ``(conversation_id, dimension, judge_prompt_hash)``.

    The judge runs offline: it always starts at ``accumulated_cost=0.0`` and uses
    the cost limit from ``eval/eval.yaml``, independent of the session's runtime cost.

    Args:
        conversation_id:   UUID of the conversation to evaluate.
        ground_truth_slug: Optional slug used to compute ``operation_recall`` and pass
                           GT context to the judge.

    Raises:
        ValueError: If the conversation row is not found.
    """
    harness_cfg = load_eval_harness_config()

    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"conversation {conversation_id} not found")

    ground_truth = get_ground_truth_by_slug(ground_truth_slug) if ground_truth_slug else None

    total_cost = compute_cost(conversation_id)
    num_turns = compute_num_turns(conversation_id)
    num_ops = compute_num_operations(conversation_id)
    clarifier_rate = compute_clarifier_trigger_rate(conversation_id)
    operation_recall = compute_operation_recall(conversation_id, ground_truth)

    clustering_m = None
    if conversation.current_cluster_snapshot_id is not None:
        clustering_m = compute_clustering_metrics(conversation.current_cluster_snapshot_id)

    upsert_conversation_metrics(
        conversation_id=conversation_id,
        final_num_clusters=clustering_m.final_num_clusters if clustering_m else 0,
        operation_recall=operation_recall,
        clarifier_trigger_rate=clarifier_rate,
        num_turns=num_turns,
        num_operations=num_ops,
        total_cost_usd=total_cost,
    )

    judge_result = await judge_conversation(
        conversation_id=conversation_id,
        ground_truth_intent_description=ground_truth.intent_description if ground_truth else None,
        ground_truth_operations=ground_truth.operations if ground_truth else None,
    )

    for dimension, (score, rationale) in judge_result.scores.items():
        insert_judge_score(
            conversation_id=conversation_id,
            dimension=dimension,
            score=score,
            judge_model=harness_cfg.judge.name,
            judge_prompt_hash=judge_result.prompt_hash,
            rationale=rationale,
        )

    log.info(
        "conversation_evaluated",
        extra={
            "conversation_id": str(conversation_id),
            "num_turns": num_turns,
            "num_operations": num_ops,
            "operation_recall": operation_recall,
            "final_num_clusters": clustering_m.final_num_clusters if clustering_m else 0,
        },
    )
