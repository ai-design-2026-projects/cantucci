"""
Per-turn orchestration. One TurnRunner instance per run_turn call.

All state used during a turn is held as explicit ``self.*`` attributes so
the flow in ``run()`` reads as a flat dispatch table: each ``if`` branch
ends in one ``_terminate_*`` or ``_finalize_turn`` call, and each of those
maps to a single observable outcome (hard limit, natural end, drift
clarification, empty clusters, ask, show).

The runner is constructed once, used once, and discarded — never reused
across turns. The Orchestrator owns construction; the runner owns the
turn-scoped state and the async task graph for the turn.
"""
import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

import backend.api.sessions as api_sessions
from backend.api.types import ClusterRow, SessionRow, StepType, TurnRow
from backend.decision import decision_agent
from backend.decision.types import DecisionAction
from backend.orchestrator.utils import presentation, speculative, terminal_paths
from backend.orchestrator.utils.progress import (
    NullProgressCallback,
    ProgressCallback,
    ProgressPhase,
    ProgressStep,
    make_progress_event,
)
from backend.orchestrator.utils.speculative import SpeculativeBranch
from backend.orchestrator.utils import history
from backend.profile import profile_agent
from backend.profile.types import UserProfile
from backend.routers.dtos import RecommendationDto, TurnDto
from backend.settings import Settings, get_settings
from backend.state import state_agent
from backend.state.types import StateAction, StateDecision

log = logging.getLogger(__name__)

class TurnRunner:
    """
    One turn of orchestration. Constructed and discarded per call.
    Never shared across turns. The Orchestrator's ``run_turn`` is a 
    thin wrapper that loads ``full``, instantiates a runner, and awaits ``run()``.
    """
    session_id: UUID
    user_message: str
    progress_cb: ProgressCallback
    # Session State at the turn's start
    turn_id: UUID
    turn_number: int
    cfg: Settings
    full_session: SessionRow
    prior_profile: dict | None
    recent_turns: list[TurnRow]
    prior_clustered: TurnRow | None
    prior_seen: list[str]
    recommended_last_turn: list[str]
    # Task handles for the parallel branches; used to await results or cancel on failure.
    state_check_task: asyncio.Task | None      
    profile_task: asyncio.Task | None    
    speculative_branch_kind: SpeculativeBranch         
    speculative_task: asyncio.Task | None

    def __init__(
        self,
        *,
        session_id: UUID,
        user_message: str,
        full_session: SessionRow,
        progress_cb: ProgressCallback = NullProgressCallback(),
    ) -> None:
        """Capture inputs and derive all per-turn state up-front.
        Every helper on the runner reads from these attributes 
        rather than re-querying the DB or re-deriving state.
        """
        self.session_id = session_id
        self.user_message = user_message
        self.progress_cb = progress_cb
        self.full_session = full_session

        self.turn_id = uuid4()
        self.turn_number = len(self.full_session.turns) + 1
        self.cfg = get_settings()
        self.prior_profile = self.full_session.preference_profile
        self.recent_turns = self.full_session.turns[-2:]
        self.prior_clustered = history.last_clustered_turn(self.full_session.turns)
        self.prior_seen = (
            list(self.prior_profile.get("seen_films", [])) if self.prior_profile else []
        )
        self.recommended_last_turn = history.recommended_titles_from_last_show(self.full_session)

        self.state_check_task = None
        self.profile_task = None
        self.speculative_branch_kind = SpeculativeBranch.NONE
        self.speculative_task = None

        log.debug(
            "turn entry",
            extra={
                "session_id": str(session_id),
                "turn_id": str(self.turn_id),
                "turn_number": self.turn_number,
                "user_message_len": len(user_message),
                "prior_turns": len(self.full_session.turns),
            },
        )
        
        if self.prior_clustered is not None:
            log.info(
                "refining prior clusters",
                extra={
                    "session_id": str(session_id),
                    "turn_number": self.turn_number,
                    "prior_clustered_turn_id": str(self.prior_clustered.id),
                },
            )


    async def run(self) -> TurnDto:
        """
        Run one turn as an async task graph, returning the result.
        Branch dispatch (each ``if`` ends a path):
          1. Hard limit                → ``_terminate_hard_limit``
          2. State gate: natural_end   → ``_terminate_natural_end``
          3. State gate: clarify_drift → ``_terminate_drift``
          4. Empty cluster set         → ``_terminate_empty_clusters``
          5. Decision agent verdict    → ``_finalize_turn`` (ask or show)
        """
        # Branch 1 — synchronous hard-limit gate, no LLM work
        hard = state_agent.check_hard_limits(
            turn_number=self.turn_number, full=self.full_session, cfg=self.cfg,
        )
        if hard.action is StateAction.terminate:
            return await self._terminate_hard_limit(hard)

        # Emit the first progress event
        self._emit(ProgressStep.UNDERSTAND, "start")
        # Spawn the async tasks for UNDERSTAND in parallel 
        # (state check, profile extraction, speculative retrieval)
        self._spawn_understand_tasks()
        
        # Await the state check; it may short-circuit the turn or even the session.
        state = await self._await_session_state_check()
        # Branch 2 - The state gate classified this as a natural session end; no LLM work needed
        if state.action is StateAction.natural_end:
            return await self._terminate_natural_end(state)
        # Branch 3 - The state gate detected a preference drift; 
        # no LLM work needed but we do need to emit a clarification turn
        if state.action is StateAction.clarify_drift:
            return await self._terminate_drift(state)

        # Non-terminal: profile is needed for re-retrieval and persistence
        new_profile = await self._await_profile()
        clusters = await speculative.resolve_clusters(
            state=state, runner=self, new_profile=new_profile,
        )
        self._emit(ProgressStep.UNDERSTAND, "end")

        # Branch 4 — retrieval / clustering returned nothing
        if not clusters:
            return await self._terminate_empty_clusters()

        # Branch 5 — normal pipeline: emit the cluster snapshot, run the decision agent
        presentation.emit_cluster_snapshot(clusters, self.progress_cb)
        return await self._finalize_turn(clusters, new_profile)


    def _spawn_understand_tasks(self) -> None:
        """Schedule session state checking, profile extraction, and the speculative branch."""
        # Check the session state in parallel
        self.state_check_task = asyncio.create_task(
            state_agent.check_session_state(
                session_id=self.session_id,
                run_id=self.full_session.run_id,
                turn_id=self.turn_id,
                turn_number=self.turn_number,
                user_message=self.user_message,
                full=self.full_session,
                preference_profile=self.prior_profile,
                cfg=self.cfg,
                recommended_last_turn=self.recommended_last_turn,
                seen_films=self.prior_seen,
            ),
            name="state_gate",
        )
        # Extract the updated preference profile in parallel
        self.profile_task = asyncio.create_task(
            profile_agent.extract(
                session_id=self.session_id,
                run_id=self.full_session.run_id,
                turn_id=self.turn_id,
                turn_number=self.turn_number,
                user_message=self.user_message,
                prior_profile=self.prior_profile,
                recent_turns=self.recent_turns,
            ),
            name="profile_extract",
        )
        # Speculatively start retrieval and clustering for the most likely next step (show vs ask)
        self.speculative_branch_kind, self.speculative_task = speculative.spawn(runner=self)

    async def _await_session_state_check(self) -> StateDecision:
        """Await the state gate; on failure, kill siblings before re-raising."""
        assert self.state_check_task is not None
        try:
            return await self.state_check_task
        except BaseException:
            await speculative.cancel_and_drain(self.profile_task)
            await speculative.cancel_and_drain(self.speculative_task)
            raise

    async def _await_profile(self) -> UserProfile:
        """Await the profile task; cancel the speculative branch on failure."""
        assert self.profile_task is not None
        try:
            return await self.profile_task
        except BaseException:
            await speculative.cancel_and_drain(self.speculative_task)
            raise

    def _emit(self, step: ProgressStep, phase: ProgressPhase) -> None:
        """Fire one progress event, guarding against a misbehaving callback."""
        try:
            self.progress_cb(make_progress_event(step, phase))
        except Exception:
            log.warning(
                "progress callback failed",
                exc_info=True,
                extra={
                    "session_id": str(self.session_id),
                    "turn_id": str(self.turn_id),
                    "step": step.value,
                    "phase": phase,
                },
            )


    async def _terminate_hard_limit(self, decision: StateDecision) -> TurnDto:
        """Branch 1: hard limit tripped before any LLM call."""
        self._emit(ProgressStep.understand, "start")
        self._emit(ProgressStep.understand, "end")
        last_show = await asyncio.to_thread(
            presentation.last_show_recommendation,
            self.full_session,
            self.cfg.session.recommendation_top_k,
        )
        self._emit(ProgressStep.wrap_up, "start")
        try:
            return await asyncio.to_thread(
                terminal_paths.terminate_turn,
                session_id=self.session_id,
                turn_id=self.turn_id,
                turn_number=self.turn_number,
                user_message=self.user_message,
                decision=decision,
                recommendation=last_show,
            )
        finally:
            self._emit(ProgressStep.wrap_up, "end")

    async def _terminate_natural_end(self, decision: StateDecision) -> TurnDto:
        """Branch 2: state gate classified the message as natural session end."""
        await speculative.discard_speculative(self.speculative_task, self.speculative_kind.value)
        await speculative.discard_speculative(self.profile_task, "profile")
        self._emit(ProgressStep.understand, "end")
        last_show = await asyncio.to_thread(
            presentation.last_show_recommendation,
            self.full_session,
            self.cfg.session.recommendation_top_k,
        )
        self._emit(ProgressStep.wrap_up, "start")
        try:
            return await asyncio.to_thread(
                terminal_paths.natural_end_turn,
                session_id=self.session_id,
                turn_id=self.turn_id,
                turn_number=self.turn_number,
                user_message=self.user_message,
                decision=decision,
                preference_profile=self.prior_profile or {},
                recommendation=last_show,
            )
        finally:
            self._emit(ProgressStep.wrap_up, "end")

    async def _terminate_drift(self, decision: StateDecision) -> TurnDto:
        """Branch 3: state gate detected a preference contradiction."""
        await speculative.discard_speculative(self.speculative_task, self.speculative_kind.value)
        await speculative.discard_speculative(self.profile_task, "profile")
        self._emit(ProgressStep.understand, "end")
        self._emit(ProgressStep.wrap_up, "start")
        try:
            return await asyncio.to_thread(
                terminal_paths.emit_drift_clarification,
                session_id=self.session_id,
                turn_id=self.turn_id,
                turn_number=self.turn_number,
                user_message=self.user_message,
                decision=decision,
            )
        finally:
            self._emit(ProgressStep.wrap_up, "end")

    async def _terminate_empty_clusters(self) -> TurnDto:
        """Branch 4: retrieval / clustering returned no candidates."""
        self._emit(ProgressStep.wrap_up, "start")
        try:
            return await asyncio.to_thread(
                terminal_paths.emit_early_clarification,
                session_id=self.session_id,
                turn_id=self.turn_id,
                turn_number=self.turn_number,
                user_message=self.user_message,
            )
        finally:
            self._emit(ProgressStep.wrap_up, "end")

    async def _finalize_turn(
        self,
        clusters: list[ClusterRow],
        new_profile: UserProfile,
    ) -> TurnDto:
        """Branch 5: persist clusters, run decision agent, render ask or show.

        The only remaining inner branch is ``DecisionAction.continue_`` →
        ask vs anything-else → show
        """
        await self._persist_turn_and_clusters(clusters)

        self._emit(ProgressStep.choose, "start")
        decision = await decision_agent.decide(
            session_id=self.session_id,
            run_id=self.full_session.run_id,
            turn_id=self.turn_id,
            turn_number=self.turn_number,
            user_query=self.user_message,
            clusters=clusters,
            preference_profile=self.prior_profile,
            prior_questions=history.prior_questions(self.full_session.turns),
        )
        log.debug(
            "decision action chosen",
            extra={
                "session_id": str(self.session_id),
                "turn_id": str(self.turn_id),
                "action": decision.action.value,
                "entropy_score": decision.entropy_score,
            },
        )

        reply: str
        step_type: StepType
        recommendation: RecommendationDto | None = None

        if decision.action == DecisionAction.continue_:
            reply = decision.question_text or ""
            step_type = StepType.ask
        else:
            best_cluster = next(
                (c for c in clusters if c.id == decision.best_cluster_id),
                clusters[0],
            )
            reply = presentation.render_recommendation(
                best_cluster=best_cluster,
                top_k=self.cfg.session.recommendation_top_k,
            )
            rendered_titles = [
                a.title
                for a in sorted(
                    [a for a in best_cluster.assignments if not a.excluded],
                    key=lambda a: a.score,
                    reverse=True,
                )[: self.cfg.session.recommendation_top_k]
                if a.title
            ]
            new_profile.seen_films = list(
                dict.fromkeys(new_profile.seen_films + rendered_titles)
            )
            step_type = StepType.show
            recommendation = await asyncio.to_thread(
                presentation.build_recommendation,
                best_cluster,
                self.cfg.session.recommendation_top_k,
            )

        converged = False
        log.debug(
            "state verdict",
            extra={
                "session_id": str(self.session_id),
                "turn_id": str(self.turn_id),
                "converged": converged,
                "step_type": step_type.value,
            },
        )
        self._emit(ProgressStep.choose, "end")

        self._emit(ProgressStep.finalize, "start")
        await asyncio.to_thread(
            api_sessions.update_turn,
            turn_id=self.turn_id,
            assistant_message=reply,
            step_type=step_type.value,
            converged=converged,
        )

        new_profile.seen_films = list(
            dict.fromkeys(
                self.prior_seen + new_profile.anchor_films + new_profile.seen_films
            )
        )
        await asyncio.to_thread(
            api_sessions.update_preference_profile,
            self.session_id,
            new_profile.model_dump(),
        )
        self._emit(ProgressStep.finalize, "end")

        log.debug(
            "profile updated",
            extra={
                "session_id": str(self.session_id),
                "turn_id": str(self.turn_id),
                "n_constraints": len(new_profile.constraints),
            },
        )

        now = datetime.now(timezone.utc)
        log.info(
            "turn handled",
            extra={
                "session_id": str(self.session_id),
                "turn_number": self.turn_number,
                "step_type": step_type.value,
                "converged": converged,
            },
        )
        return TurnDto(
            turn_id=self.turn_id,
            session_id=self.session_id,
            turn_number=self.turn_number,
            user_message=self.user_message,
            assistant_message=reply,
            step_type=step_type,
            converged=converged,
            created_at=now,
            recommendation=recommendation,
        )

    async def _persist_turn_and_clusters(
        self,
        clusters: list[ClusterRow],
    ) -> None:
        """Write the placeholder turn row + cluster snapshot.

        Reply text and step_type are filled in by ``_finalize_turn`` after
        the decision agent runs.
        """
        await asyncio.to_thread(
            api_sessions.append_turn,
            session_id=self.session_id,
            turn_number=self.turn_number,
            user_message=self.user_message,
            assistant_message=None,
            step_type=None,
            converged=False,
            turn_id=self.turn_id,
        )
        await asyncio.to_thread(
            api_sessions.snapshot_clusters,
            self.session_id,
            self.turn_id,
            [c.to_spec() for c in clusters],
        )
        log.debug(
            "cluster snapshot persisted",
            extra={
                "session_id": str(self.session_id),
                "turn_id": str(self.turn_id),
                "n_clusters": len(clusters),
            },
        )


__all__ = ["TurnRunner"]
