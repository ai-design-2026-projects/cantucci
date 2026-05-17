"""Orchestrator — DB-backed, policy-driven coordinator for conversational sessions.

No in-memory session state: all persistence flows through ``backend.api``.

Turn flow (per architecture.md):
  Oracle → Orchestrator → Convergence Agent → Cluster Agent (→ Retrieval
  internally) → Decision Agent (decides + generates question when continuing) →
  Profile Agent → Orchestrator writes turn / clusters / feedback / profile.

The Orchestrator is the sole writer to the DB. All sub-agents are read-only.
Private decision logic lives in ``backend/orchestrator/tools/``.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import backend.api.retrieval as api_retrieval
import backend.api.runs as api_runs
import backend.api.sessions as api_sessions
from backend.cluster import cluster_agent
from backend.convergence import convergence_agent
from backend.decision import decision_agent
from backend.profile import profile_agent
from backend.api.types import ClusterSnapshot, SessionStatus, StepType, TurnDetail
from backend.convergence.types import ConvergenceAction, ConvergenceDecision
from backend.decision.types import DecisionAction
from backend.exceptions import SessionNotFound
from backend.routers.dtos import SessionState, TurnResult
from backend.orchestrator.progress import (
    NullProgressCallback,
    ProgressCallback,
    ProgressPhase,
    ProgressStep,
    make_progress_event,
)
from backend.orchestrator.tools.feedback import classify_feedback
from backend.orchestrator.tools.policy import (
    cluster_snapshot_to_spec,
    prior_questions,
    should_retrieve,
)
from backend.orchestrator.tools.render import render_recommendation
from backend.orchestrator.tools.turns import emit_drift_clarification, emit_early_clarification
from backend.settings import get_config_hash, get_config_snapshot, get_settings

log = logging.getLogger(__name__)


def _prior_clusters_from_turn(turn: TurnDetail) -> list[ClusterSnapshot]:
    """Return the ClusterSnapshots stored on a prior turn."""
    return list(turn.clusters)


class Orchestrator:
    """LLM-backed orchestrator. No in-memory session state; all persistence in DB.

    Each ``create_session`` call inserts one run + one session row. In the full
    system, runs are managed externally and ``create_session`` accepts a run_id.
    For the scaffold, a run is created implicitly per interactive session.
    """

    def create_session(self) -> SessionState:
        """Create a run + session row and return the initial SessionState.

        Loads the default config for model, seed, and session parameters.

        Returns:
            A ``SessionState`` with status=active and an empty turn list.
        """
        cfg = get_settings()
        config_hash = get_config_hash()
        config_snapshot = get_config_snapshot()

        run_id = api_runs.create_run(
            name="interactive",
            condition="baseline",
            config_snapshot=config_snapshot,
            config_hash=config_hash,
            seed=cfg.models.strong.seed,
            model_version=cfg.models.strong.name,
        )

        now = datetime.now(timezone.utc)
        session_id = api_sessions.create_session(
            run_id=run_id,
            seed=cfg.models.strong.seed,
            config_hash=config_hash,
            model_version=cfg.models.strong.name,
            max_turns=cfg.session.max_turns,
            cost_limit_usd=Decimal(str(cfg.session.cost_limit_usd)),
        )

        log.info(
            "session created",
            extra={"session_id": str(session_id), "run_id": str(run_id)},
        )
        return SessionState(
            session_id=session_id,
            status=SessionStatus.active,
            max_turns=cfg.session.max_turns,
            created_at=now,
            updated_at=now,
            turns=[],
        )

    def handle_turn(
        self,
        session_id: UUID,
        user_message: str,
        *,
        progress_cb: ProgressCallback = NullProgressCallback(),
    ) -> TurnResult:
        """Orchestrate one conversational turn and persist all resulting state.

        Full flow:
          1. Load session state from DB.
          2. Convergence Agent: hard-limit + LLM gate (uses N-1 profile).
          3. Retrieval/cluster decision.
          4. Cluster Agent (Scenario A or B).
          5. Decision Agent: decides action and, when continuing, generates the question.
          6. Profile Agent: extract updated profile → persist on session.
          7. Persist the turn and oracle feedback.

        Args:
            session_id:   UUID of the target session.
            user_message: The oracle's message for this turn.
            progress_cb:  Invoked at the start and end of each wave so the
                          router can stream ``ProgressEvent`` lines to the
                          live-state frontend. Defaults to ``NullProgressCallback``
                          so non-streaming callers (tests, eval scripts) are
                          unaffected. Must be thread-safe and must not raise.

        Returns:
            A ``TurnResult`` describing the outcome of this turn.

        Raises:
            SessionNotFound:   If *session_id* does not exist in the DB.
            CostLimitExceeded: If the session budget is exhausted.
            LLMParseError:     If any agent LLM call returns malformed JSON.
        """
        def _emit(step: ProgressStep, phase: ProgressPhase) -> None:
            try:
                progress_cb(make_progress_event(step, phase))
            except Exception:
                log.warning(
                    "progress callback failed",
                    exc_info=True,
                    extra={
                        "session_id": str(session_id),
                        "turn_id": str(turn_id),
                        "step": step.value,
                        "phase": phase,
                    },
                )

        full = api_retrieval.get_session_full(session_id)

        turn_id = uuid4()
        turn_number = len(full.turns) + 1
        cfg = get_settings()

        # N-1 profile (may be None on the first turn)
        prior_profile = full.preference_profile

        # Short history: last 2 completed turns
        recent_turns: list[TurnDetail] = full.turns[-2:]

        log.debug(
            "turn entry",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "turn_number": turn_number,
                "user_message_len": len(user_message),
                "prior_turns": len(full.turns),
            },
        )

        # Precompute pure cluster inputs so Wave 1 can dispatch immediately.
        prior_turn = full.turns[-1] if full.turns else None
        is_refinement = (
            prior_turn is not None
            and prior_turn.step_type == StepType.ask.value
            and prior_turn.clusters
        )
        ret = should_retrieve(full, user_message)

        if is_refinement:
            log.info(
                "refinement after ask",
                extra={"session_id": str(session_id), "turn_number": turn_number},
            )
            cluster_kwargs: dict = dict(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_query=user_message,
                prior_clusters=_prior_clusters_from_turn(prior_turn),
                asked_question=prior_turn.assistant_message or "",
                user_answer=user_message,
            )
        else:
            log.info(
                "fresh retrieval",
                extra={
                    "session_id": str(session_id),
                    "turn_number": turn_number,
                    "retrieve_new": ret.retrieve,
                },
            )
            cluster_kwargs = dict(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_query=ret.query or user_message,
            )

        # Wave 1: Convergence + Cluster (speculative) + Profile in parallel.
        # Convergence is read first; if it is terminal the speculative results
        # are discarded. We still drain those futures (try/except) so threads
        # are not leaked. Exceptions in speculative work are only silenced when
        # the result is discarded — on the proceed path they propagate normally.
        _emit(ProgressStep.understand, "start")
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_conv = pool.submit(
                convergence_agent.check,
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
                full=full,
                preference_profile=prior_profile,
                cfg=cfg,
            )
            f_cluster = pool.submit(cluster_agent.cluster, **cluster_kwargs)
            f_profile = pool.submit(
                profile_agent.extract,
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
                prior_profile=prior_profile,
                recent_turns=recent_turns,
            )
            conv = f_conv.result()

            _terminal = conv.action in (
                ConvergenceAction.terminate,
                ConvergenceAction.natural_end,
                ConvergenceAction.clarify_drift,
            )
            if _terminal:
                for _f, _name in ((f_cluster, "cluster"), (f_profile, "profile")):
                    try:
                        _f.result()
                    except Exception as _exc:
                        log.warning(
                            "speculative agent failed (discarded — convergence terminal)",
                            extra={
                                "agent": _name,
                                "session_id": str(session_id),
                                "error": str(_exc),
                            },
                        )
                clusters = []
                new_profile = prior_profile
            else:
                clusters = f_cluster.result()
                new_profile = f_profile.result()
        _emit(ProgressStep.understand, "end")

        if conv.action is ConvergenceAction.terminate:
            _emit(ProgressStep.wrap_up, "start")
            try:
                return self._terminate_turn(
                    session_id=session_id,
                    turn_id=turn_id,
                    turn_number=turn_number,
                    user_message=user_message,
                    decision=conv,
                )
            finally:
                _emit(ProgressStep.wrap_up, "end")

        if conv.action is ConvergenceAction.natural_end:
            _emit(ProgressStep.wrap_up, "start")
            try:
                return self._natural_end_turn(
                    session_id=session_id,
                    turn_id=turn_id,
                    turn_number=turn_number,
                    user_message=user_message,
                    decision=conv,
                    preference_profile=prior_profile or {},
                )
            finally:
                _emit(ProgressStep.wrap_up, "end")

        if conv.action is ConvergenceAction.clarify_drift:
            _emit(ProgressStep.wrap_up, "start")
            try:
                return emit_drift_clarification(
                    session_id=session_id,
                    turn_id=turn_id,
                    turn_number=turn_number,
                    user_message=user_message,
                    decision=conv,
                )
            finally:
                _emit(ProgressStep.wrap_up, "end")

        # Convergence ↔ Cluster reconciliation: if convergence supplies a
        # retrieval override, the speculative cluster result is stale — rerun.
        if conv.retrieval_override:
            log.warning(
                "cluster rerun: convergence supplied retrieval override",
                extra={
                    "session_id": str(session_id),
                    "turn_id": str(turn_id),
                    "override_query": conv.retrieval_override,
                },
            )
            clusters = cluster_agent.cluster(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_query=conv.retrieval_override,
            )

        if not clusters:
            _emit(ProgressStep.wrap_up, "start")
            try:
                return emit_early_clarification(
                    session_id=session_id,
                    turn_id=turn_id,
                    turn_number=turn_number,
                    user_message=user_message,
                )
            finally:
                _emit(ProgressStep.wrap_up, "end")

        api_sessions.append_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=None,
            step_type=None,
            converged=False,
            turn_id=turn_id,
        )

        api_sessions.snapshot_clusters(
            session_id, turn_id, [cluster_snapshot_to_spec(c) for c in clusters]
        )

        log.debug(
            "cluster snapshot persisted",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "n_clusters": len(clusters),
            },
        )

        _emit(ProgressStep.choose, "start")
        decision = decision_agent.decide(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_query=user_message,
            clusters=clusters,
            preference_profile=prior_profile,
            prior_questions=prior_questions(full.turns),
        )

        log.debug(
            "decision action chosen",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "action": decision.action.value,
                "entropy_score": decision.entropy_score,
            },
        )

        reply: str
        step_type: StepType
        converged: bool

        if decision.action == DecisionAction.continue_:
            reply = decision.question_text or ""
            step_type = StepType.ask
            converged = False
        else:
            best_cluster = next(
                (c for c in clusters if c.id == decision.best_cluster_id),
                clusters[0],
            )
            reply = render_recommendation(
                best_cluster=best_cluster,
                decision=decision,
                top_k=cfg.session.recommendation_top_k,
            )
            converged = False
            step_type = StepType.show

        log.debug(
            "convergence verdict",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "converged": converged,
                "step_type": step_type.value,
            },
        )
        _emit(ProgressStep.choose, "end")

        _emit(ProgressStep.finalize, "start")
        api_sessions.update_turn(
            turn_id=turn_id,
            assistant_message=reply,
            step_type=step_type.value,
            converged=converged,
        )

        fb_level, fb_type, fb_target_id = classify_feedback(full.turns, user_message, decision)
        api_sessions.write_feedback(
            session_id=session_id,
            turn_id=turn_id,
            feedback_level=fb_level,
            feedback_type=fb_type,
            content=user_message,
            target_id=fb_target_id,
        )

        api_sessions.update_preference_profile(session_id, new_profile.model_dump())
        _emit(ProgressStep.finalize, "end")

        log.debug(
            "profile updated",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "n_constraints": len(new_profile.constraints),
            },
        )

        now = datetime.now(timezone.utc)
        log.info(
            "turn handled",
            extra={
                "session_id": str(session_id),
                "turn_number": turn_number,
                "step_type": step_type.value,
                "converged": converged,
            },
        )
        return TurnResult(
            turn_id=turn_id,
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type,
            converged=converged,
            created_at=now,
        )

    def _terminate_turn(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        turn_number: int,
        user_message: str,
        decision: ConvergenceDecision,
    ) -> TurnResult:
        """Persist and return a terminal turn when a hard limit is reached.

        Writes step_type=stop, converged=False and marks the session abandoned.
        No LLM call is made.

        Args:
            session_id:   UUID of the target session.
            turn_id:      Pre-allocated turn UUID.
            turn_number:  1-based index for this turn.
            user_message: Oracle's message that triggered the limit check.
            decision:     ConvergenceDecision from check_hard_limits.

        Returns:
            A TurnResult with step_type=stop, converged=False.
        """
        reply = decision.reply or "Session limit reached. Thank you for using CinePal!"
        step_type = StepType.stop
        api_sessions.append_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type.value,
            converged=False,
            turn_id=turn_id,
        )
        api_sessions.mark_abandoned(session_id, decision.reason)
        log.warning(
            "turn terminated: hard limit",
            extra={
                "session_id": str(session_id),
                "turn_number": turn_number,
                "reason": decision.reason,
            },
        )
        now = datetime.now(timezone.utc)
        log.info(
            "turn handled",
            extra={
                "session_id": str(session_id),
                "turn_number": turn_number,
                "step_type": step_type.value,
                "converged": False,
            },
        )
        return TurnResult(
            turn_id=turn_id,
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type,
            converged=False,
            created_at=now,
        )

    def _natural_end_turn(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        turn_number: int,
        user_message: str,
        decision: ConvergenceDecision,
        preference_profile: dict,
    ) -> TurnResult:
        """Persist and return a convergence turn detected by the LLM gate.

        Writes step_type=stop, converged=True, marks the session converged,
        and records an accept feedback row.

        Args:
            session_id:        UUID of the target session.
            turn_id:           Pre-allocated turn UUID.
            turn_number:       1-based index for this turn.
            user_message:      Oracle's message that the gate classified as natural end.
            decision:          ConvergenceDecision from the convergence agent.
            preference_profile: N-1 profile to persist with the converged session.

        Returns:
            A TurnResult with step_type=stop, converged=True.
        """
        reply = decision.reply or "Thank you — closing the session!"
        step_type = StepType.stop
        api_sessions.append_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type.value,
            converged=True,
            turn_id=turn_id,
        )
        api_sessions.write_feedback(
            session_id=session_id,
            turn_id=turn_id,
            feedback_level="global",
            feedback_type="accept",
            content=user_message,
            target_id=None,
        )
        api_sessions.mark_converged(session_id, preference_profile)
        log.info(
            "turn handled",
            extra={
                "session_id": str(session_id),
                "turn_number": turn_number,
                "step_type": step_type.value,
                "converged": True,
            },
        )
        now = datetime.now(timezone.utc)
        return TurnResult(
            turn_id=turn_id,
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type,
            converged=True,
            created_at=now,
        )

    def get_session(self, session_id: UUID) -> SessionState:
        """Return full session state including all turns from the DB.

        Args:
            session_id: UUID of the session to retrieve.

        Returns:
            A ``SessionState`` with turns in ascending turn_number order.

        Raises:
            SessionNotFound: If *session_id* does not exist in the DB.
        """
        try:
            full = api_retrieval.get_session_full(session_id)
        except ValueError as exc:
            raise SessionNotFound(session_id) from exc

        turns = [
            TurnResult(
                turn_id=t.id,
                session_id=session_id,
                turn_number=t.turn_number,
                user_message=t.user_message,
                assistant_message=t.assistant_message or "",
                step_type=StepType(t.step_type) if t.step_type else StepType.show,
                converged=t.converged,
                created_at=t.created_at,
            )
            for t in full.turns
        ]

        return SessionState(
            session_id=full.session_id,
            status=SessionStatus(full.status),
            max_turns=full.max_turns,
            created_at=full.created_at,
            updated_at=full.updated_at,
            turns=turns,
        )
