"""Evaluation runner: drives simulated oracle sessions and scores completed conversations.

The runner calls directly into the live system's data-access and coordinator
layers (the same path the HTTP router uses) so simulated sessions are
indistinguishable from human sessions in the database.
"""
import logging
import uuid

from backend.agents.coordinator.agent import Coordinator
from backend.data_access.conversations.queries import (
    add_conversation_cost,
    append_message,
    create_conversation,
    get_conversation,
)
from backend.data_access.evaluation.queries import (
    create_eval_session,
    get_ground_truth_by_slug,
    get_persona_by_slug,
    insert_judge_score,
    set_eval_session_status,
    upsert_conversation_metrics,
)
from backend.settings import get_config_snapshot, get_settings
from eval.judge.agent import judge_conversation
from eval.metrics import (
    compute_clustering_metrics,
    compute_convergence,
    compute_cost,
    compute_spec_satisfaction,
)
from eval.oracle.agent import oracle_turn

log = logging.getLogger(__name__)


async def run_simulated_session(
    run_id: uuid.UUID,
    persona_slug: str,
    ground_truth_slug: str,
    seed: int,
    user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Drive a full simulated oracle session and evaluate it.

    Creates a conversation, links it to the eval run, drives oracle turns until
    the oracle accepts, abandons, or the turn budget is exhausted, then calls
    ``evaluate_conversation`` to compute and persist all metrics.

    Args:
        run_id:             Parent eval run UUID.
        persona_slug:       Slug of the oracle persona to use.
        ground_truth_slug:  Slug of the ground truth to use.
        seed:               Per-session RNG seed for reproducibility.
        user_id:            Optional user UUID (None for anonymous).

    Returns:
        UUID of the created conversation.

    Raises:
        ValueError: If the persona or ground truth slug is not found.
    """
    cfg = get_settings()

    persona = get_persona_by_slug(persona_slug)
    if persona is None:
        raise ValueError(f"persona not found: {persona_slug!r}")

    ground_truth = get_ground_truth_by_slug(ground_truth_slug)
    if ground_truth is None:
        raise ValueError(f"ground truth not found: {ground_truth_slug!r}")

    config_snapshot = get_config_snapshot()
    conversation_id = create_conversation(user_id=user_id, config_snapshot=config_snapshot)
    eval_session_id = create_eval_session(
        run_id=run_id,
        conversation_id=conversation_id,
        seed=seed,
        persona_id=persona.id,
        ground_truth_id=ground_truth.id,
    )

    log.info(
        "simulated_session_started",
        extra={
            "conversation_id": str(conversation_id),
            "eval_session_id": str(eval_session_id),
            "persona": persona_slug,
            "ground_truth": ground_truth_slug,
            "seed": seed,
        },
    )

    coordinator = Coordinator()
    transcript: list[dict] = []
    accumulated_cost = 0.0
    final_status = "abandoned"

    for turn_number in range(1, cfg.eval.max_turns + 1):
        conversation_row = get_conversation(conversation_id)
        if conversation_row is None:
            raise RuntimeError(f"conversation {conversation_id} disappeared mid-session")

        system_message = transcript[-1]["content"] if transcript and transcript[-1]["role"] == "assistant" else ""

        oracle_result = await oracle_turn(
            persona=persona,
            ground_truth=ground_truth,
            transcript=transcript,
            system_message=system_message,
            turn_number=turn_number,
            seed=seed,
            conversation_id=str(conversation_id),
            accumulated_cost=accumulated_cost,
        )
        accumulated_cost += oracle_result.cost

        append_message(conversation_id, "user", oracle_result.message)
        transcript.append({"role": "user", "content": oracle_result.message})

        log.debug(
            "oracle_turn",
            extra={
                "conversation_id": str(conversation_id),
                "turn": turn_number,
                "intent": oracle_result.intent,
            },
        )

        if oracle_result.intent == "accept":
            final_status = "converged"
            log.info(
                "oracle_accepted",
                extra={"conversation_id": str(conversation_id), "turn": turn_number},
            )
            break

        if oracle_result.intent == "abandon":
            final_status = "abandoned"
            log.info(
                "oracle_abandoned",
                extra={"conversation_id": str(conversation_id), "turn": turn_number},
            )
            break

        coord_result = await coordinator.handle_message(
            conversation_id=conversation_id,
            user_message=oracle_result.message,
            conversation_row=conversation_row,
        )
        accumulated_cost += coord_result.turn_cost_usd

        msg_id = append_message(
            conversation_id, "assistant", coord_result.reply_text, cost_usd=coord_result.turn_cost_usd
        )
        add_conversation_cost(conversation_id, coord_result.turn_cost_usd)
        transcript.append({"role": "assistant", "content": coord_result.reply_text})

    set_eval_session_status(conversation_id, final_status)
    log.info(
        "simulated_session_ended",
        extra={"conversation_id": str(conversation_id), "status": final_status},
    )

    await evaluate_conversation(
        conversation_id=conversation_id,
        ground_truth_slug=ground_truth_slug,
        judge_cost_budget=accumulated_cost,
    )
    return conversation_id


async def evaluate_conversation(
    conversation_id: uuid.UUID,
    ground_truth_slug: str | None = None,
    judge_cost_budget: float = 0.0,
) -> None:
    """Compute and persist all deterministic metrics and judge scores for a conversation.

    Safe to call multiple times — ``upsert_conversation_metrics`` overwrites the
    previous row, and ``insert_judge_score`` is guarded by a unique constraint on
    (conversation_id, dimension, judge_prompt_hash).

    Args:
        conversation_id:   UUID of the conversation to evaluate.
        ground_truth_slug: Optional slug used to fetch the hidden spec for
                           spec_satisfaction_rate and to pass the taste description
                           to the judge.
        judge_cost_budget: Accumulated LLM cost so far, forwarded to the judge
                           harness call for cost-limit checking.
    """
    cfg = get_settings()

    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"conversation {conversation_id} not found")

    convergence = compute_convergence(conversation_id)
    total_cost = compute_cost(conversation_id)

    clustering_m = None
    if conversation.current_cluster_snapshot_id is not None:
        clustering_m = compute_clustering_metrics(conversation.current_cluster_snapshot_id)

    spec_rate: float | None = None
    ground_truth_description: str | None = None
    if ground_truth_slug is not None:
        gt = get_ground_truth_by_slug(ground_truth_slug)
        if gt is not None:
            ground_truth_description = gt.description
            if conversation.current_cluster_snapshot_id is not None:
                spec_rate = compute_spec_satisfaction(
                    conversation.current_cluster_snapshot_id,
                    gt.spec,
                    gt.target_movie_ids,
                )

    upsert_conversation_metrics(
        conversation_id=conversation_id,
        silhouette=clustering_m.silhouette if clustering_m else None,
        mean_membership_prob=clustering_m.mean_membership_prob if clustering_m else None,
        noise_fraction=clustering_m.noise_fraction if clustering_m else None,
        final_num_clusters=clustering_m.final_num_clusters if clustering_m else None,
        spec_satisfaction_rate=spec_rate,
        converged=convergence.converged,
        num_turns=convergence.num_turns,
        total_cost_usd=total_cost,
        turns_to_convergence=convergence.turns_to_convergence,
    )

    judge_result = await judge_conversation(
        conversation_id=conversation_id,
        accumulated_cost=judge_cost_budget,
        ground_truth_description=ground_truth_description,
    )

    for dimension, (score, rationale) in judge_result.scores.items():
        insert_judge_score(
            conversation_id=conversation_id,
            dimension=dimension,
            score=score,
            judge_model=cfg.models.strong.name,
            judge_prompt_hash=judge_result.prompt_hash,
            rationale=rationale,
        )

    log.info(
        "conversation_evaluated",
        extra={
            "conversation_id": str(conversation_id),
            "converged": convergence.converged,
            "turns": convergence.num_turns,
            "silhouette": clustering_m.silhouette if clustering_m else None,
        },
    )
