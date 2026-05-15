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
)
from backend.orchestrator.convergence import should_retrieve, convergence_policy
from backend.orchestrator.tools.render import render_recommendation
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
 
        #TODO: Implement a more robust policy around when to retrieve 
        if should_retrieve(full):
            # Remove the prior candidates
            prior = None
            log.info(
                "Retrieving new candidates",
                extra={
                    "session_id": str(session_id),
                    "turn_number": turn_number,
                    "reason": "first-turn" if not full.turns else "reject-feedback",
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

        # Send to cluster agent
        clusters = cluster_agent.cluster(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_query=user_message,
            prior_candidates=prior,
        )

        # If no clusters are returned, skip decision and render and return a canned clarification turn.
        if not clusters:
            return self._early_clarification_turn(
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
        api_sessions.snapshot_clusters(
            session_id, turn_id, [cluster_snapshot_to_spec(c) for c in clusters]
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

        reply: str
        step_type: StepType
        converged: bool
        # If continue, send to ambiguity resolver to generate a clarifying question.
        if decision.action == DecisionAction.continue_:
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
            # If the policy deems this turn converged, mark it as such to prevent further turns and to trigger convergence-specific UI behavior. The convergence policy can look at the full conversation history and the current decision context to make this determination.
            converged = convergence_policy(full.turns, cfg.session.convergence_turns)
            step_type = StepType.stop if converged else StepType.show

        # Persist the turn with the assistant message, step type, and convergence status
        api_sessions.update_turn(
            turn_id=turn_id,
            assistant_message=reply,
            step_type=step_type.value,
            converged=converged,
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

        # Extract the preference profile (#TODO: to use this data for decision)
        preference_profile = extract_preference_profile(
                full.turns, user_message, clusters, decision
        )
        # If converged, extract the preference profile and mark the session converged
        if converged:
            api_sessions.mark_converged(session_id, preference_profile)

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

    def _early_clarification_turn(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        turn_number: int,
        user_message: str,
    ) -> TurnResult:
        """Persist and return a canned clarifying reply when retrieval yields no candidates.

        Args:
            session_id:   UUID of the target session.
            turn_id:      Pre-allocated turn UUID.
            turn_number:  1-based index for this turn.
            user_message: Oracle's message that produced empty retrieval.

        Returns:
            A TurnResult with step_type=ask and the canned reply.
        """
        reply = (
            "I couldn't find films matching that description. "
            "Could you tell me more about the kind of films you're looking for? "
            "For example, a mood, a director's style, a genre, or an era?"
        )
        step_type = StepType.ask
        api_sessions.append_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type.value,
            converged=False,
            turn_id=turn_id,
        )
        api_sessions.write_feedback(
            session_id=session_id,
            turn_id=turn_id,
            feedback_level="global",
            feedback_type="constraint",
            content=user_message,
            target_id=None,
        )
        log.warning(
            "no clusters returned — canned clarification turn",
            extra={"session_id": str(session_id), "turn_number": turn_number},
        )
        now = datetime.now(timezone.utc)
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
