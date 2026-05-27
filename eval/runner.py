"""Evaluation runner: drives simulated oracle sessions and scores completed conversations.

The runner calls directly into the live system's data-access and coordinator
layers (the same path the HTTP router uses) so simulated sessions are
indistinguishable from human sessions in the database.
"""
import logging
import uuid

from backend.agents.coordinator.agent import Coordinator
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.conversations.queries import (
    add_conversation_cost,
    append_message,
    create_conversation,
    get_conversation,
)
from backend.data_access.eval.queries import (
    create_eval_session,
    get_ground_truth_by_slug,
    get_persona_by_slug,
    insert_judge_score,
    insert_turn_intent,
    set_eval_session_termination,
    upsert_conversation_metrics,
)
from backend.data_access.movies.queries import fetch_stubs
from backend.settings import get_config_snapshot
from eval.config import load_eval_harness_config
from eval.judge.agent import judge_conversation
from eval.metrics import (
    compute_clarifier_trigger_rate,
    compute_clustering_metrics,
    compute_cost,
    compute_num_operations,
    compute_num_turns,
    compute_operation_recall,
)
from eval.oracle.agent import oracle_turn

log = logging.getLogger(__name__)


def _build_current_snapshot_info(conversation_id: uuid.UUID) -> list[dict]:
    """Build a cluster-info list for the oracle prompt from the current snapshot.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        List of dicts with label/summary/exemplar_titles per cluster.
    """
    conversation = get_conversation(conversation_id)
    if conversation is None or conversation.current_cluster_snapshot_id is None:
        return []
    snapshot = get_cluster_snapshot_with_clusters(conversation.current_cluster_snapshot_id)
    if snapshot is None:
        return []
    result = []
    for cluster in snapshot.clusters:
        stubs = fetch_stubs(cluster.exemplar_movie_ids[:5]) if cluster.exemplar_movie_ids else []
        exemplar_titles = [f"{s.title} ({s.release_year or '?'})" for s in stubs]
        result.append({
            "label": cluster.label,
            "summary": cluster.summary,
            "exemplar_titles": exemplar_titles,
        })
    return result


def _infer_termination_status(
    oracle_decision: str,
    executed_operations: list[dict],
    ground_truth_operations: list[dict],
    hit_budget: bool,
) -> str:
    """Infer a termination status from the oracle's final decision.

    Args:
        oracle_decision:         "stop" or "continue".
        executed_operations:     Operations recorded during the session.
        ground_truth_operations: GT operations list.
        hit_budget:              True if the runner hit max_turns without the oracle stopping.

    Returns:
        One of: "finished_trajectory", "finished_misbehaviour", "finished_budget".
    """
    if hit_budget:
        return "finished_budget"

    if oracle_decision == "stop":
        executed_set = {(op["op"], op["concept"].strip().lower()) for op in executed_operations}
        gt_set = {(op["op"], op["concept"].strip().lower()) for op in ground_truth_operations}
        all_done = gt_set.issubset(executed_set)
        return "finished_trajectory" if all_done else "finished_misbehaviour"

    return "finished_budget"


async def run_simulated_session(
    run_id: uuid.UUID,
    persona_slug: str,
    ground_truth_slug: str,
    seed: int,
    condition: str = "conversational",
    user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Drive a full simulated oracle session and evaluate it.

    Creates a conversation, links it to the eval run, drives oracle turns until
    the oracle stops or the turn budget is exhausted, then calls
    ``evaluate_conversation`` to compute and persist all metrics.

    Args:
        run_id:             Parent eval run UUID.
        persona_slug:       Slug of the oracle persona to use.
        ground_truth_slug:  Slug of the ground truth to use.
        seed:               Per-session RNG seed for reproducibility.
        condition:          Experimental condition ("conversational", "no_agents", "monolithic").
        user_id:            Optional user UUID (None for anonymous).

    Returns:
        UUID of the created conversation.

    Raises:
        ValueError: If the persona or ground truth slug is not found.
    """
    harness_cfg = load_eval_harness_config()

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
        condition=condition,
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
            "condition": condition,
        },
    )

    if condition == "conversational":
        system_handler = _ConversationalHandler()
    elif condition == "no_agents":
        from backend.baseline.no_agents.runner import NoAgentsHandler
        system_handler = NoAgentsHandler()
    elif condition == "monolithic":
        from backend.baseline.monolithic.runner import MonolithicHandler
        system_handler = MonolithicHandler()
    else:
        raise ValueError(f"unknown condition: {condition!r}")

    transcript: list[dict] = []
    accumulated_cost = 0.0
    executed_operations: list[dict] = []
    last_oracle_decision = "continue"
    last_oracle_rationale = ""
    last_oracle_rating: int | None = None
    hit_budget = False

    for turn_number in range(1, harness_cfg.runner.max_turns + 1):
        conversation_row = get_conversation(conversation_id)
        if conversation_row is None:
            raise RuntimeError(f"conversation {conversation_id} disappeared mid-session")

        current_snapshot_info = _build_current_snapshot_info(conversation_id)

        oracle_result = await oracle_turn(
            persona=persona,
            ground_truth=ground_truth,
            transcript=transcript,
            executed_operations=executed_operations,
            current_snapshot=current_snapshot_info,
            turn_number=turn_number,
            conversation_id=conversation_id,
            accumulated_cost=accumulated_cost,
        )
        accumulated_cost += oracle_result.cost
        last_oracle_decision = oracle_result.decision
        last_oracle_rationale = oracle_result.rationale
        last_oracle_rating = oracle_result.session_rating

        append_message(conversation_id, "user", oracle_result.message)
        transcript.append({"role": "user", "content": oracle_result.message})

        log.debug(
            "oracle_turn",
            extra={
                "conversation_id": str(conversation_id),
                "turn": turn_number,
                "decision": oracle_result.decision,
            },
        )

        if oracle_result.decision == "stop":
            log.info("oracle_stopped", extra={"conversation_id": str(conversation_id), "turn": turn_number})
            break

        system_result = await system_handler.handle_turn(
            conversation_id=conversation_id,
            user_message=oracle_result.message,
            conversation_row=conversation_row,
        )
        accumulated_cost += system_result.turn_cost_usd

        append_message(
            conversation_id,
            "assistant",
            system_result.reply_text,
            cost_usd=system_result.turn_cost_usd,
        )
        add_conversation_cost(conversation_id, system_result.turn_cost_usd)
        transcript.append({"role": "assistant", "content": system_result.reply_text})

        if system_result.turn_trace is not None:
            trace = system_result.turn_trace
            for mode in trace.modes:
                concept_idx = trace.modes.index(mode)
                concept = trace.concepts[concept_idx] if concept_idx < len(trace.concepts) else None
                target_id = trace.target_cluster_ids[concept_idx] if concept_idx < len(trace.target_cluster_ids) else None
                insert_turn_intent(
                    conversation_id=conversation_id,
                    turn_number=turn_number,
                    mode=mode,
                    confidence=trace.confidence,
                    raw_intent=trace.raw_intent,
                    concept=concept,
                    target_cluster_id=target_id,
                    clarifier_fired=trace.clarifier_fired,
                )
                if mode in {"drill_down", "merge", "focus", "cross_filter"} and concept:
                    executed_operations.append({"op": mode, "concept": concept})
    else:
        hit_budget = True

    termination_status = _infer_termination_status(
        oracle_decision=last_oracle_decision,
        executed_operations=executed_operations,
        ground_truth_operations=ground_truth.operations,
        hit_budget=hit_budget,
    )

    set_eval_session_termination(
        eval_session_id=eval_session_id,
        status=termination_status,
        rationale=last_oracle_rationale,
        oracle_rating=last_oracle_rating,
    )

    log.info(
        "simulated_session_ended",
        extra={
            "conversation_id": str(conversation_id),
            "status": termination_status,
            "oracle_rating": last_oracle_rating,
        },
    )

    await evaluate_conversation(
        conversation_id=conversation_id,
        ground_truth_slug=ground_truth_slug,
    )
    return conversation_id


async def evaluate_conversation(
    conversation_id: uuid.UUID,
    ground_truth_slug: str | None = None,
) -> None:
    """Compute and persist all deterministic metrics and judge scores for a conversation.

    Safe to call multiple times — ``upsert_conversation_metrics`` overwrites the
    previous row, and ``insert_judge_score`` is guarded by a unique constraint on
    (conversation_id, dimension, judge_prompt_hash).

    The judge runs offline: it always starts at accumulated_cost=0.0 and uses the
    cost limit from eval/eval.yaml, independent of the session's runtime cost.

    Args:
        conversation_id:   UUID of the conversation to evaluate.
        ground_truth_slug: Optional slug used to compute operation_recall and pass
                           GT context to the judge.
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
        silhouette=clustering_m.silhouette if clustering_m else None,
        mean_membership_prob=clustering_m.mean_membership_prob if clustering_m else None,
        noise_fraction=clustering_m.noise_fraction if clustering_m else None,
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
            "silhouette": clustering_m.silhouette if clustering_m else None,
        },
    )


class _ConversationalHandler:
    """Adapts Coordinator.handle_message to the session-driver turn protocol."""

    def __init__(self) -> None:
        self._coordinator = Coordinator()

    async def handle_turn(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        conversation_row,
    ):
        from backend.baseline.shared.types import SystemTurnResult

        result = await self._coordinator.handle_message(
            conversation_id=conversation_id,
            user_message=user_message,
            conversation_row=conversation_row,
        )
        return SystemTurnResult(
            reply_text=result.reply_text,
            suggestion=result.suggestion,
            turn_trace=result.turn_trace,
            turn_cost_usd=result.turn_cost_usd,
            cluster_snapshot_id=result.cluster_snapshot_id,
        )
