"""Orchestrator — DB-backed, policy-driven coordinator for conversational sessions.

No in-memory session state: all persistence flows through ``backend.api``.

Turn flow (per architecture.md):
  Oracle → Orchestrator → Cluster Agent (→ Retrieval internally) →
  Decision Agent → (Ambiguity Resolver if continue) → Orchestrator → DB/UI.

The Orchestrator is the sole writer to the DB. All sub-agents are read-only.
Private decision logic lives in ``backend/orchestrator/tools/``.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import backend.api.retrieval as api_retrieval
import backend.api.runs as api_runs
import backend.api.sessions as api_sessions
from backend.ambiguity import ambiguity_agent
from backend.cluster import cluster_agent
from backend.decision import decision_agent
from backend.api.types import SessionStatus, StepType
from backend.decision.types import DecisionAction
from backend.exceptions import SessionNotFound
from backend.routers.dtos import SessionState, TurnResult
from backend.orchestrator.tools.feedback import classify_feedback, extract_preference_profile
from backend.orchestrator.tools.policy import (
    cluster_snapshot_to_spec,
    collect_prior_candidates,
    prior_questions,
    should_retrieve,
)
from backend.orchestrator.tools.convergence import check_hard_limits, check_llm_convergence
from backend.orchestrator.tools.render import render_recommendation
from backend.orchestrator.tools.turns import emit_drift_clarification, emit_early_clarification
from backend.orchestrator.types import ConvergenceAction, ConvergenceDecision
from backend.settings import get_config_hash, get_config_snapshot, get_settings

log = logging.getLogger(__name__)


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
            seed=cfg.model.seed,
            model_version=cfg.model.name,
        )

        now = datetime.now(timezone.utc)
        session_id = api_sessions.create_session(
            run_id=run_id,
            seed=cfg.model.seed,
            config_hash=config_hash,
            model_version=cfg.model.name,
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

    def handle_turn(self, session_id: UUID, user_message: str) -> TurnResult:
        """Orchestrate one conversational turn and persist all resulting state.

        Full flow:
          1. Load session state from DB.
          2. Build a refined retrieval query from the conversation history.
          3. Cluster Agent retrieves candidates and clusters them (or reuses prior
             candidates when no reject feedback has been given).
          4. Persist the cluster snapshot (before downstream use).
          5. Decision Agent routes to recommend or continue.
          6. If continue: Ambiguity Resolver generates a clarifying question (deduped).
             If recommend: render a presentation reply; evaluate convergence policy.
          7. Persist the turn.
          8. Classify and persist oracle feedback.
          9. If converged: extract preference profile and mark session converged.

        Args:
            session_id:   UUID of the target session.
            user_message: The oracle's message for this turn.

        Returns:
            A ``TurnResult`` describing the outcome of this turn.

        Raises:
            SessionNotFound:   If *session_id* does not exist in the DB.
            CostLimitExceeded: If the session budget is exhausted.
            LLMParseError:     If any agent LLM call returns malformed JSON.
        """
        # Load full session state for orchestration and logging context.
        full = api_retrieval.get_session_full(session_id)

        # Pre-allocate a turn_id for log correlation across steps and agents.
        turn_id = uuid4()
        turn_number = len(full.turns) + 1
        cfg = get_settings()

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

        # If any hard limits are breached, skip the turn and return a terminal reply.
        hard = check_hard_limits(turn_number=turn_number, full=full, cfg=cfg)
        if hard.action is ConvergenceAction.terminate:
            return self._terminate_turn(
                session_id=session_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
                decision=hard,
            )

        # Check for convergence via the LLM gate. If converged, return a terminal reply.
        prior_profile = extract_preference_profile(full.turns, user_message)
        llm_gate = check_llm_convergence(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_message=user_message,
            full=full,
            preference_profile=prior_profile,
            cfg=cfg,
        )

        # If we have a natural end, we can skip retrieval
        if llm_gate.action is ConvergenceAction.natural_end:
            return self._natural_end_turn(
                session_id=session_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
                decision=llm_gate,
                preference_profile=prior_profile,
            )
        
        # If we have drift, we can also skip retrieval and go straight to clarification.
        if llm_gate.action is ConvergenceAction.clarify_drift:
            return emit_drift_clarification(
                session_id=session_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
                decision=llm_gate,
            )

        ret = should_retrieve(full, user_message)
        if ret.retrieve:
            prior = None
            log.info(
                "Retrieving new candidates",
                extra={
                    "session_id": str(session_id),
                    "turn_number": turn_number,
                    "reason": "first-turn" if not full.turns else "post-drift",
                },
            )
        else:
            # Reuse the prior candidates
            prior = collect_prior_candidates(full.turns[-1])
            log.info(
                "reusing prior candidates",
                extra={
                    "session_id": str(session_id),
                    "turn_number": turn_number,
                    "n_candidates": len(prior),
                    "reason": "no-reject-feedback",
                },
            )

        log.debug(
            "retrieval decision resolved",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "retrieve_new": prior is None,
                "n_prior_candidates": 0 if prior is None else len(prior),
            },
        )

        # Send to cluster agent; on post-drift retrieval, use the drift message as the
        # query so retrieval targets the new preference rather than the clarification reply.
        clusters = cluster_agent.cluster(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_query=ret.query or user_message,
            prior_candidates=prior,
        )

        # If no clusters are returned, skip decision and render and return a canned clarification turn.
        if not clusters:
            return emit_early_clarification(
                session_id=session_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
            )

        # Persist the turn with the user message and cluster snapshot
        api_sessions.append_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=None,
            step_type=None,
            converged=False,
            turn_id=turn_id,
        )

        # Persist the cluster snapshot for this turn so that it's available for downstream analysis 
        api_sessions.snapshot_clusters(
            session_id, turn_id, [cluster_snapshot_to_spec(c) for c in clusters]
        )

        log.debug(
            "cluster snapshot persisted",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "n_clusters": len(clusters),
                "top_cluster_size": max((len(c.assignments) for c in clusters), default=0),
            },
        )

        # Decision Agent routes to recommend vs. continue (clarifying question).
        decision = decision_agent.decide(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_query=user_message,
            clusters=clusters,
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
        # If continue, send to ambiguity resolver to generate a clarifying question.
        if decision.action == DecisionAction.continue_:
            log.debug(
                "entering ambiguity branch",
                extra={
                    "session_id": str(session_id),
                    "turn_id": str(turn_id),
                    "n_prior_questions": len(prior_questions(full.turns)),
                },
            )
            # Generate the question, ensuring it's not a duplicate of any prior questions in this session to avoid infinite loops. If it is a duplicate, log a warning and fallback to rendering a recommendation instead.
            question = ambiguity_agent.generate_question(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_query=user_message,
                clusters=clusters,
                entropy_score=decision.entropy_score,
                prior_questions=prior_questions(full.turns),
            )
            # Return the question
            reply = question.question_text
            step_type = StepType.ask
            converged = False
        else:
        # Else if recommend, render the recommendation reply and evaluate convergence.
            llm_out = render_recommendation(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
                history=full.turns,
                persona_id=full.persona_id,
                decision=decision,
                clusters=clusters,
            )
            reply = llm_out.reply
            # Convergence is now decided by the LLM gate at the top of the next
            # turn; the render step always writes show (not stop).
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

        # Persist the turn with the assistant message, step type, and convergence status
        api_sessions.update_turn(
            turn_id=turn_id,
            assistant_message=reply,
            step_type=step_type.value,
            converged=converged,
        )
        log.debug(
            "turn row updated",
            extra={"session_id": str(session_id), "turn_id": str(turn_id)},
        )

        # Classify and persist feedback
        fb_level, fb_type, fb_target_id = classify_feedback(full.turns, user_message, decision)
        api_sessions.write_feedback(
            session_id=session_id,
            turn_id=turn_id,
            feedback_level=fb_level,
            feedback_type=fb_type,
            content=user_message,
            target_id=fb_target_id,
        )
        log.debug(
            "feedback written",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "feedback_level": fb_level,
                "feedback_type": fb_type,
                "target_id": str(fb_target_id) if fb_target_id else None,
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
            decision:          ConvergenceDecision from check_llm_convergence.
            preference_profile: Rolling profile extracted before the pipeline ran.

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
