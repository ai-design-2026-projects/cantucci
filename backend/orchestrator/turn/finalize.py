"""Post-decision rendering and persistence for a normal turn.

Once UNDERSTAND has produced a non-empty cluster set, ``finalize`` runs
the decision agent, renders ``ask`` or ``show``, persists the turn and
profile, and returns the ``TurnDto`` for the HTTP response. All
progress events (``choose`` and ``finalize``) are emitted from here so
the runner stays a thin dispatcher.

Pure async — DB writes are hopped into threads via ``asyncio.to_thread``
since the underlying ``api_sessions`` helpers are sync.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import backend.api.sessions as api_sessions
from backend.api.types import ClusterRow, StepType
from backend.decision import decision_agent
from backend.decision.types import DecisionAction, DecisionResult
from backend.orchestrator.turn.context import TurnContext
from backend.orchestrator.utils import history, presentation
from backend.orchestrator.turn.progress import ProgressPhase, ProgressStep, make_progress_event
from backend.profile.types import UserProfile
from backend.routers.dtos import RecommendationDto, TurnDto

log = logging.getLogger(__name__)


async def finalize(
    ctx: TurnContext,
    clusters: list[ClusterRow],
    new_profile: UserProfile,
) -> TurnDto:
    """Run decision → render → persist for a normal (non-bypass) turn.

    Args:
        ctx:         Frozen per-turn snapshot.
        clusters:    Non-empty cluster list produced by UNDERSTAND.
        new_profile: Freshly extracted profile (mutated in place when the
                     decision is ``show`` to record the rendered titles).

    Returns:
        Fully assembled ``TurnDto`` ready for the HTTP response.
    """
    await _persist_placeholder_turn(ctx, clusters)

    _emit(ctx, ProgressStep.CHOOSE, "start")
    decision = await _run_decision(ctx, clusters)

    if decision.action == DecisionAction.continue_:
        reply, step_type, recommendation = _build_ask(decision)
    else:
        reply, step_type, recommendation = await _build_show(
            ctx, clusters, decision, new_profile,
        )
    _emit(ctx, ProgressStep.CHOOSE, "end")

    _emit(ctx, ProgressStep.FINALIZE, "start")
    await _persist_turn_and_profile(ctx, reply, step_type, new_profile)
    _emit(ctx, ProgressStep.FINALIZE, "end")

    log.info(
        "turn handled",
        extra={
            "session_id": str(ctx.session_id),
            "turn_number": ctx.turn_number,
            "step_type": step_type.value,
            "converged": False,
        },
    )
    return TurnDto(
        turn_id=ctx.turn_id,
        session_id=ctx.session_id,
        turn_number=ctx.turn_number,
        user_message=ctx.user_message,
        assistant_message=reply,
        step_type=step_type,
        converged=False,
        created_at=datetime.now(timezone.utc),
        recommendation=recommendation,
    )


async def _persist_placeholder_turn(
    ctx: TurnContext,
    clusters: list[ClusterRow],
) -> None:
    """Write the placeholder turn row + cluster snapshot.

    Reply text and step_type are filled in by ``_persist_turn_and_profile``
    after the decision agent runs.
    """
    await asyncio.to_thread(
        api_sessions.append_turn,
        session_id=ctx.session_id,
        turn_number=ctx.turn_number,
        user_message=ctx.user_message,
        assistant_message=None,
        step_type=None,
        converged=False,
        turn_id=ctx.turn_id,
    )
    await asyncio.to_thread(
        api_sessions.snapshot_clusters,
        ctx.session_id,
        ctx.turn_id,
        [c.to_spec() for c in clusters],
    )
    log.debug(
        "cluster snapshot persisted",
        extra={
            "session_id": str(ctx.session_id),
            "turn_id": str(ctx.turn_id),
            "n_clusters": len(clusters),
        },
    )


async def _run_decision(
    ctx: TurnContext,
    clusters: list[ClusterRow],
) -> DecisionResult:
    """Invoke the decision agent and log its verdict."""
    decision = await decision_agent.decide(
        session_id=ctx.session_id,
        run_id=ctx.full_session.run_id,
        turn_id=ctx.turn_id,
        turn_number=ctx.turn_number,
        user_query=ctx.user_message,
        clusters=clusters,
        preference_profile=ctx.prior_profile,
        prior_questions=history.prior_questions(ctx.full_session.turns),
    )
    log.debug(
        "decision action chosen",
        extra={
            "session_id": str(ctx.session_id),
            "turn_id": str(ctx.turn_id),
            "action": decision.action.value,
            "entropy_score": decision.entropy_score,
        },
    )
    return decision


def _build_ask(decision: DecisionResult) -> tuple[str, StepType, RecommendationDto | None]:
    """Render the clarifying-question reply when the decision agent says continue."""
    return decision.question_text or "", StepType.ask, None


async def _build_show(
    ctx: TurnContext,
    clusters: list[ClusterRow],
    decision: DecisionResult,
    new_profile: UserProfile,
) -> tuple[str, StepType, RecommendationDto | None]:
    """Render the show-turn reply, append rendered titles to ``new_profile.seen_films``.

    Picks the cluster whose id matches ``decision.best_cluster_id``,
    falling back to the first cluster when the id is missing — exactly
    the same fallback as the pre-refactor code path.
    """
    best_cluster = next(
        (c for c in clusters if c.id == decision.best_cluster_id),
        clusters[0],
    )
    reply = presentation.render_recommendation(
        best_cluster=best_cluster,
        top_k=ctx.cfg.session.recommendation_top_k,
    )
    rendered_titles = [
        a.title
        for a in sorted(
            [a for a in best_cluster.assignments if not a.excluded],
            key=lambda a: a.score,
            reverse=True,
        )[: ctx.cfg.session.recommendation_top_k]
        if a.title
    ]
    new_profile.seen_films = list(
        dict.fromkeys(new_profile.seen_films + rendered_titles)
    )
    recommendation = await asyncio.to_thread(
        presentation.build_recommendation,
        best_cluster,
        ctx.cfg.session.recommendation_top_k,
    )
    return reply, StepType.show, recommendation


async def _persist_turn_and_profile(
    ctx: TurnContext,
    reply: str,
    step_type: StepType,
    new_profile: UserProfile,
) -> None:
    """Finalise the turn row and persist the merged preference profile.

    The seen-films merge dedupes ``prior_seen ++ anchors ++ seen_films``
    while preserving order, matching the pre-refactor behaviour.
    """
    await asyncio.to_thread(
        api_sessions.update_turn,
        turn_id=ctx.turn_id,
        assistant_message=reply,
        step_type=step_type.value,
        converged=False,
    )
    new_profile.seen_films = list(
        dict.fromkeys(
            ctx.prior_seen + new_profile.anchor_films + new_profile.seen_films
        )
    )
    await asyncio.to_thread(
        api_sessions.update_preference_profile,
        ctx.session_id,
        new_profile.model_dump(),
    )
    log.debug(
        "profile updated",
        extra={
            "session_id": str(ctx.session_id),
            "turn_id": str(ctx.turn_id),
            "n_constraints": len(new_profile.constraints),
        },
    )


def _emit(ctx: TurnContext, step: ProgressStep, phase: ProgressPhase) -> None:
    """Fire one progress event, guarding against a misbehaving callback."""
    try:
        ctx.progress_cb(make_progress_event(step, phase))
    except Exception:
        log.warning(
            "progress callback failed",
            exc_info=True,
            extra={
                "session_id": str(ctx.session_id),
                "turn_id": str(ctx.turn_id),
                "step": step.value,
                "phase": phase,
            },
        )


__all__ = ["finalize"]
