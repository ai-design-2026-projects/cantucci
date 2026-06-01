"""Single simulated oracle session driver.

Drives one complete oracle session against the live system and evaluates it at
the end.  Calls the same Coordinator and data-access path as live HTTP sessions
so simulated sessions are indistinguishable from human sessions in the database.
"""
import logging
import uuid

from backend.data_access.concepts.queries import get_concept, get_concept_axis_points
from backend.data_access.conversations.queries import (
    add_conversation_cost,
    append_message,
    create_conversation,
    get_conversation,
    get_messages,
)
from backend.data_access.eval.queries import (
    create_eval_session,
    get_ground_truth_by_slug,
    get_persona_by_slug,
    insert_turn_intent,
    set_eval_session_termination,
)
from backend.settings import get_config_snapshot
from eval.config import load_eval_harness_config
from eval.oracle.agent import oracle_turn
from eval.runtime.evaluate import evaluate_conversation
from eval.runtime.handlers import select_handler
from eval.runtime.snapshot import build_cluster_info
from eval.runtime.termination import infer_termination_status
from eval.types import NAVIGATION_OPERATIONS

log = logging.getLogger(__name__)


async def run_simulated_session(
    run_id: uuid.UUID,
    persona_slug: str,
    ground_truth_slug: str,
    seed: int,
    condition: str = "conversational",
    user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Drive a full simulated oracle session and evaluate it at the end.

    Creates a conversation in the unclustered state (NULL snapshot), links it to the
    eval run, then drives oracle turns until the oracle stops or the turn budget is
    exhausted.  Calls ``evaluate_conversation`` automatically after the session ends.

    Args:
        run_id:             Parent eval run UUID.
        persona_slug:       Slug of the bundle to use as oracle persona.
        ground_truth_slug:  Slug of the bundle's ground truth.
        seed:               Per-session RNG seed for reproducibility.
        condition:          Experimental condition (``"conversational"``, ``"baseline"``).
        user_id:            Optional user UUID (``None`` for anonymous).

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

    system_handler = select_handler(condition)

    transcript: list[dict] = []
    accumulated_cost = 0.0
    evolution_trace: list[dict] = []
    last_oracle_decision = "continue"
    last_oracle_rationale = ""
    last_oracle_rating: int | None = None
    hit_budget = False

    exemplar_k = harness_cfg.runner.exemplar_top_k

    for turn_number in range(1, harness_cfg.runner.max_turns + 1):
        conversation_row = get_conversation(conversation_id)
        if conversation_row is None:
            raise RuntimeError(f"conversation {conversation_id} disappeared mid-session")

        current_snapshot: list[dict] = []
        if conversation_row.current_cluster_snapshot_id is not None:
            current_snapshot = build_cluster_info(
                conversation_row.current_cluster_snapshot_id,
                exemplar_k=exemplar_k,
            )

        pending_axis: dict | None = None
        last_messages = get_messages(conversation_id, limit=1)
        last_axis_concept_id = (
            last_messages[-1].axis_concept_id
            if last_messages and last_messages[-1].role == "assistant"
            else None
        )
        if last_axis_concept_id is not None:
            concept = get_concept(last_axis_concept_id)
            if concept is not None:
                pole_k = harness_cfg.scorer.pole_sample_k
                points = get_concept_axis_points(concept.id)
                points_sorted = sorted(points, key=lambda p: p.score, reverse=True)
                pending_axis = {
                    "concept_name": concept.name,
                    "top_titles": [p.title for p in points_sorted[:pole_k]],
                    "bottom_titles": [p.title for p in reversed(points_sorted[-pole_k:])],
                }

        oracle_result = await oracle_turn(
            persona=persona,
            ground_truth=ground_truth,
            transcript=transcript,
            evolution_trace=evolution_trace,
            current_snapshot=current_snapshot,
            turn_number=turn_number,
            conversation_id=conversation_id,
            accumulated_cost=accumulated_cost,
            pending_axis=pending_axis,
        )
        accumulated_cost += oracle_result.cost
        last_oracle_decision = oracle_result.decision
        last_oracle_rationale = oracle_result.rationale
        last_oracle_rating = oracle_result.session_rating

        append_message(conversation_id, "user", oracle_result.message)
        transcript.append({"role": "user", "content": oracle_result.message})

        log.debug(
            "oracle_turn_completed",
            extra={
                "conversation_id": str(conversation_id),
                "turn": turn_number,
                "decision": oracle_result.decision,
            },
        )

        if oracle_result.decision == "stop":
            log.info(
                "oracle_stopped",
                extra={"conversation_id": str(conversation_id), "turn": turn_number},
            )
            break

        try:
            system_result = await system_handler.handle_turn(
                conversation_id=conversation_id,
                user_message=oracle_result.message,
                conversation_row=conversation_row,
            )
        except RuntimeError as exc:
            fallback = f"The operation could not be completed: {exc}. Please try a different approach."
            log.warning("system_turn_failed_non_fatal", extra={"conversation_id": str(conversation_id), "turn": turn_number, "error": str(exc)})
            append_message(conversation_id, "assistant", fallback)
            transcript.append({"role": "assistant", "content": fallback})
            continue

        accumulated_cost += system_result.turn_cost_usd

        append_message(
            conversation_id,
            "assistant",
            system_result.reply_text,
            cost_usd=system_result.turn_cost_usd,
            suggestion=system_result.suggestion,
            axis_concept_id=system_result.axis_concept_id,
        )
        add_conversation_cost(conversation_id, system_result.turn_cost_usd)
        oracle_content = system_result.reply_text
        if system_result.suggestion:
            oracle_content = oracle_content.replace(system_result.suggestion, "").strip()
        transcript.append({"role": "assistant", "content": oracle_content})

        if system_result.turn_trace is not None:
            trace = system_result.turn_trace
            turn_modes: list[str] = []
            turn_concepts: list[str] = []
            for idx, mode in enumerate(trace.modes):
                concept = trace.concepts[idx] if idx < len(trace.concepts) else None
                target_id = trace.target_cluster_ids[idx] if idx < len(trace.target_cluster_ids) else None
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
                if mode in NAVIGATION_OPERATIONS:
                    turn_modes.append(mode)
                    turn_concepts.append(concept or "")
            if turn_modes:
                evolution_trace.append({
                    "turn": turn_number,
                    "modes": turn_modes,
                    "concepts": turn_concepts,
                })
    else:
        hit_budget = True

    termination_status = infer_termination_status(
        oracle_decision=last_oracle_decision,
        oracle_rating=last_oracle_rating,
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
