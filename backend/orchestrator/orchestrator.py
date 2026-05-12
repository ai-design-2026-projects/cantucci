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
from backend.llm.configs import load_config
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
        """Load history, call agent, record turn, return TurnResult.

        Args:
            session_id:   UUID of the target session.
            user_message: The oracle's message.

        Returns:
            A ``TurnResult`` with the LLM's reply and step_type=show.

        Raises:
            SessionNotFound:   If *session_id* does not exist in the DB.
            CostLimitExceeded: If the session budget is exhausted before the call.
        """
        try:
            full = api_retrieval.get_session_full(session_id)
        except ValueError as exc:
            raise SessionNotFound(session_id) from exc

        turn_id = uuid4()
        turn_number = len(full.turns) + 1

        assistant_text = agent.respond(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_message=user_message,
            history=full.turns,
            persona_id=full.persona_id,
            config_hash=full.config_hash,
            model_version=full.model_version,
        )

        state_tools.record_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=assistant_text,
            step_type=StepType.show.value,
            converged=False,
            turn_id=turn_id,
        )

        now = datetime.now(timezone.utc)
        log.info(
            "turn handled",
            extra={"session_id": str(session_id), "turn_number": turn_number},
        )
        return TurnResult(
            turn_id=turn_id,
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=assistant_text,
            step_type=StepType.show,
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
