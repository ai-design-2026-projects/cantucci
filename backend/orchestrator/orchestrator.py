"""Real Orchestrator — DB-backed, LLM-driven coordinator.

Implements the ``backend.models.orchestrator.Orchestrator`` Protocol.
No in-memory session state: all persistence flows through ``backend.api``.
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
from backend.llm.configs import load_config
from backend.models.decision import DecisionAction
from backend.models.exceptions import SessionNotFound
from backend.models.sessions import SessionState, SessionStatus, StepType, TurnResult
from backend.orchestrator import agent
from backend.orchestrator.tools import state as state_tools

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
        cfg, config_hash = load_config("default")

        run_id = api_runs.create_run(
            name="interactive",
            condition="baseline",
            config_snapshot=cfg,
            seed=cfg["model"]["seed"],
            model_version=cfg["model"]["name"],
        )

        now = datetime.now(timezone.utc)
        session_id = api_sessions.create_session(
            run_id=run_id,
            seed=cfg["model"]["seed"],
            config_hash=config_hash,
            model_version=cfg["model"]["name"],
            max_turns=cfg["session"]["max_turns"],
            cost_limit_usd=Decimal(str(cfg["session"]["cost_limit_usd"])),
        )

        log.info(
            "session created",
            extra={"session_id": str(session_id), "run_id": str(run_id)},
        )
        return SessionState(
            session_id=session_id,
            status=SessionStatus.active,
            max_turns=cfg["session"]["max_turns"],
            created_at=now,
            updated_at=now,
            turns=[],
        )

    def handle_turn(self, session_id: UUID, user_message: str) -> TurnResult:
        """Load history, call Decision Agent + Orchestrator agent, record turn.

        Args:
            session_id:   UUID of the target session.
            user_message: The oracle's message.

        Returns:
            A ``TurnResult`` with the LLM's reply, mapped step_type, and
            convergence flag.

        Raises:
            SessionNotFound:   If *session_id* does not exist in the DB.
            CostLimitExceeded: If the session budget is exhausted before the call.
            LLMParseError:     If the orchestrator LLM returns malformed JSON.
        """
        try:
            full = api_retrieval.get_session_full(session_id)
        except ValueError as exc:
            raise SessionNotFound(session_id) from exc

        turn_id = uuid4()
        turn_number = len(full.turns) + 1

        clusters = cluster_agent.cluster(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            candidates=[],
            config_hash=full.config_hash,
            model_version=full.model_version,
        )

        decision = decision_agent.decide(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_query=user_message,
            clusters=clusters,
            config_hash=full.config_hash,
            model_version=full.model_version,
        )

        reply: str
        converged: bool
        preference_profile: dict | None

        if decision.action == DecisionAction.continue_:
            prior_questions = [
                t.assistant_message
                for t in full.turns
                if t.step_type == StepType.ask.value and t.assistant_message
            ]
            question = ambiguity_agent.generate_question(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_query=user_message,
                clusters=clusters,
                entropy_score=decision.entropy_score,
                prior_questions=prior_questions,
                config_hash=full.config_hash,
                model_version=full.model_version,
            )
            reply, converged, preference_profile = question.question_text, False, None
            step_type = StepType.ask
        else:
            llm_out = agent.respond(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
                history=full.turns,
                persona_id=full.persona_id,
                config_hash=full.config_hash,
                model_version=full.model_version,
                max_turns=full.max_turns,
                decision=decision,
            )
            reply, converged, preference_profile = (
                llm_out.reply,
                llm_out.converged,
                llm_out.preference_profile,
            )
            step_type = StepType.stop if converged else StepType.show

        state_tools.record_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type.value,
            converged=converged,
            turn_id=turn_id,
        )

        if converged:
            assert preference_profile is not None  # guaranteed by agent.respond
            state_tools.declare_convergence(session_id, preference_profile)

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
