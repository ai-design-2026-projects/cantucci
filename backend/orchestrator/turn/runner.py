"""
Per-turn coordinator. The orchestrator's run_turn constructs a new TurnRunner for each 
incoming message, and throws it away after the turn completes. This class is responsible for:
- Spawning and awaiting the turn's tasks (retrieval, clustering, state checks, etc.)
- Emitting progress events at the right times
- Branching to the right terminal path, if any (hard limit, natural end, drift, empty clusters)
- Calling the finalizer if we get that far
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import UUID

from backend.orchestrator.turn import finalize as finalize_mod
from backend.orchestrator.turn.context import TurnContext
from backend.orchestrator.turn.tasks import TurnTasks
from backend.orchestrator.turn import terminal_paths
from backend.profile.types import UserProfile
from backend.orchestrator.turn.progress import (
    NullProgressCallback,
    ProgressCallback,
    ProgressPhase,
    ProgressStep,
    make_progress_event,
)
from backend.routers.dto.sessions.builders import emit_cluster_snapshot, last_show_recommendation
from backend.routers.dto.sessions.dtos import TurnDto
from backend.state import state_agent
from backend.state.types import StateAction, StateDecision

log = logging.getLogger(__name__)


class TurnRunner:
    """One-shot per-turn coordinator. Constructed by ``Orchestrator.run_turn``."""
    ctx: TurnContext
    tasks: TurnTasks

    def __init__(
        self,
        *,
        session_id: UUID,
        user_message: str,
        full_session,
        progress_cb: ProgressCallback = NullProgressCallback(),
    ) -> None:
        """Freeze the per-turn snapshot and bind a fresh task tracker."""
        self.ctx = TurnContext.build(
            session_id=session_id,
            user_message=user_message,
            full_session=full_session,
            progress_cb=progress_cb,
        )
        self.tasks = TurnTasks(self.ctx)

    async def run(self) -> TurnDto:
        """Run one turn. Returns the assembled ``TurnDto``.

        Branch dispatch (each ``if`` ends a path):
          1. Hard limit                → ``_hard_limit``
          2. State gate: natural_end   → ``_natural_end``
          3. State gate: clarify_drift → ``_drift``
          4. Empty cluster set         → ``_empty_clusters``
          5. Decision agent verdict    → ``finalize`` (ask or show)
        """
        ctx = self.ctx

        # Check HARD limits before doing any work
        hard = state_agent.check_hard_limits(
            turn_number=ctx.turn_number, full=ctx.full_session, cfg=ctx.cfg,
        )
        if hard.action is StateAction.terminate:
            return await self._hard_limit(hard)
        
        # If we pass the hard limit check, emit UNDERSTAND event and spawn the tasks.
        self._emit(ProgressStep.UNDERSTAND, "start")
        self._emit(ProgressStep.RETRIEVING, "start")
        self.tasks.spawn()
        state = await self.tasks.await_state()

        # State agent identified a natural end -> discard all tasks and branch to natural end path
        if state.action is StateAction.natural_end:
            await self.tasks.discard_all()
            return await self._natural_end(state)
        # State agent identified a drift -> discard all tasks and branch to drift clarification path
        if state.action is StateAction.clarify_drift:
            await self.tasks.discard_all()
            return await self._drift(state)

        # Otherwise, we proceed to await the profile and clusters
        new_profile = await self.tasks.await_profile()
        self._emit(ProgressStep.RETRIEVING, "end")
        self._emit(ProgressStep.CLUSTERING, "start")
        clusters = await self.tasks.resolve_clusters(state, new_profile)
        self._emit(ProgressStep.CLUSTERING, "end")
        self._emit(ProgressStep.UNDERSTAND, "end")

        if not clusters:
            return await self._empty_clusters()

        # If we have clusters, emit a snapshot for the frontend before finalizing the turn
        emit_cluster_snapshot(clusters, ctx.progress_cb)
        return await finalize_mod.finalize(ctx, clusters, new_profile)


    async def _hard_limit(self, decision: StateDecision) -> TurnDto:
        """
        Branch 1: hard limit tripped before any LLM call. We recommend the 
        last-shown items as a fallback, which is arguably better than showing nothing at all.
        """
        ctx = self.ctx
        # Retrieve the last-shown recommendation to use as a fallback
        last_show = await asyncio.to_thread(
            last_show_recommendation,
            ctx.full_session,
        )
        async with self._wrap_up():
            return await asyncio.to_thread(
                terminal_paths.terminate_turn,
                session_id=ctx.session_id,
                turn_id=ctx.turn_id,
                turn_number=ctx.turn_number,
                user_message=ctx.user_message,
                decision=decision,
                recommendation=last_show,
            )

    async def _natural_end(self, decision: StateDecision) -> TurnDto:
        """Branch 2: state classified the message as natural session end."""
        ctx = self.ctx
        # Early emit the end of the UNDERSTAND step, since we won't be doing any more work related to understanding the message
        self._emit(ProgressStep.UNDERSTAND, "end")
        # Retrieve the last-shown recommendation to use as a fallback, in case the finalizer needs it to construct the natural end response
        last_show = await asyncio.to_thread(
            last_show_recommendation,
            ctx.full_session,
        )
        async with self._wrap_up():
            return await asyncio.to_thread(
                terminal_paths.natural_end_turn,
                session_id=ctx.session_id,
                turn_id=ctx.turn_id,
                turn_number=ctx.turn_number,
                user_message=ctx.user_message,
                decision=decision,
                preference_profile=ctx.prior_profile or UserProfile(constraints=[], preferences=[], attitudes=[], summary=""),
                recommendation=last_show,
            )

    async def _drift(self, decision: StateDecision) -> TurnDto:
        """Branch 3: state gate detected a preference contradiction. We """
        ctx = self.ctx
        self._emit(ProgressStep.UNDERSTAND, "end")
        async with self._wrap_up():
            return await asyncio.to_thread(
                terminal_paths.emit_drift_clarification,
                session_id=ctx.session_id,
                turn_id=ctx.turn_id,
                turn_number=ctx.turn_number,
                user_message=ctx.user_message,
                decision=decision,
            )

    async def _empty_clusters(self) -> TurnDto:
        """Branch 4: retrieval / clustering returned no candidates."""
        ctx = self.ctx
        async with self._wrap_up():
            return await asyncio.to_thread(
                terminal_paths.emit_early_clarification,
                session_id=ctx.session_id,
                turn_id=ctx.turn_id,
                turn_number=ctx.turn_number,
                user_message=ctx.user_message,
            )

    @asynccontextmanager
    async def _wrap_up(self):
        """Bracket a terminal-path call with ``wrap_up`` start/end events."""
        self._emit(ProgressStep.WRAP_UP, "start")
        try:
            yield
        finally:
            self._emit(ProgressStep.WRAP_UP, "end")

    def _emit(self, step: ProgressStep, phase: ProgressPhase) -> None:
        """Fire one progress event, guarding against a misbehaving callback."""
        try:
            self.ctx.progress_cb(make_progress_event(step, phase))
        except Exception:
            log.warning(
                "progress callback failed",
                exc_info=True,
                extra={
                    "session_id": str(self.ctx.session_id),
                    "turn_id": str(self.ctx.turn_id),
                    "step": step.value,
                    "phase": phase,
                },
            )


__all__ = ["TurnRunner"]
