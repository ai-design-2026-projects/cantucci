"""
Orchestrator — public surface for session lifecycle and per-turn execution.
The Orchestrator owns three endpoints worth of behaviour:
    - create_session: open a run + session row and return the initial state.
    - run_turn: load the session snapshot, instantiate a TurnRunner,
        and await one turn's execution.
    - get_session: hydrate every persisted turn into the HTTP DTO shape,
        atching all movie-metadata fetches into one DB call.

The class itself is stateless — no in-memory session state, no module-level
caches. All persistence flows through ``backend.api``; every turn is
replayable from its stored seed + config snapshot + turn history alone.
"""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import backend.api.retrieval as api_retrieval
import backend.api.runs as api_runs
import backend.api.sessions as api_sessions
from backend.api.types import SessionStatus
from backend.exceptions import SessionNotFound
from backend.orchestrator.utils import presentation
from backend.orchestrator.turn.progress import NullProgressCallback, ProgressCallback
from backend.orchestrator.turn import TurnRunner
from backend.routers.dtos import SessionDto, TurnDto
from backend.settings import get_config_hash, get_config_snapshot, get_settings

log = logging.getLogger(__name__)


class Orchestrator:
    """Stateless coordinator. One process-wide instance shared across all
    sessions; per-turn state lives in a fresh ``TurnRunner`` per call.
    """

    def create_session(self, user_id: UUID | None = None) -> SessionDto:
        """Create a run + session row and return the initial SessionDto.

        Loads the default config for model, seed, and session parameters.

        Args:
            user_id: Authenticated user who owns this session; None for anonymous.

        Returns:
            A ``SessionDto`` with status=active and an empty turn list.
        """
        cfg = get_settings()
        config_hash = get_config_hash()
        config_snapshot = get_config_snapshot()

        # Create a new run for this session so we can group it with eval runs in the future.
        run_id = api_runs.create_run(
            name="interactive",
            condition="baseline",
            config_snapshot=config_snapshot,
            config_hash=config_hash,
            seed=cfg.models.strong.seed,
            model_version=cfg.models.strong.name,
        )

        now = datetime.now(timezone.utc)
        # Create the session row with a reference to the run we just created.
        session_id = api_sessions.create_session(
            run_id=run_id,
            seed=cfg.models.strong.seed,
            config_hash=config_hash,
            model_version=cfg.models.strong.name,
            max_turns=cfg.session.max_turns,
            cost_limit_usd=Decimal(str(cfg.session.cost_limit_usd)),
            user_id=user_id,
        )

        log.info(
            "session created",
            extra={"session_id": str(session_id), "run_id": str(run_id)},
        )
        # Return the initial session state with an empty turn list.
        return SessionDto(
            session_id=session_id,
            status=SessionStatus.active,
            max_turns=cfg.session.max_turns,
            created_at=now,
            updated_at=now,
            turns=[],
        )
    

    async def run_turn(
        self,
        session_id: UUID,
        user_message: str,
        *,
        progress_cb: ProgressCallback = NullProgressCallback(),
    ) -> TurnDto:
        """Load the session snapshot and run one turn via a fresh ``TurnRunner``.
        The runner holds all per-turn state and owns the async task graph
        Args:
            session_id:   UUID of the target session.
            user_message: The oracle's message for this turn.
            progress_cb:  Invoked at the start and end of each progress step.
                          Called on the event loop thread; must not block or raise.
        Returns:
            A ``TurnDto`` describing the outcome of this turn.
        Raises:
            SessionNotFound:   If *session_id* does not exist in the DB.
            CostLimitExceeded: If the session budget is exhausted.
            LLMParseError:     If any agent LLM call returns malformed JSON.
        """

        full_session = await asyncio.to_thread(api_retrieval.get_session_full, session_id)
        runner = TurnRunner(
            session_id=session_id,
            user_message=user_message,
            full_session=full_session,
            progress_cb=progress_cb,
        )
        return await runner.run()

    def get_session(self, session_id: UUID) -> SessionDto:
        """Return full session state including all turns from the DB.
        Args:
            session_id: UUID of the session to retrieve.
        Returns:
            A ``SessionDto`` with turns in ascending turn_number order.
        Raises:
            SessionNotFound: If *session_id* does not exist in the DB.
        """
        try:
            full_session = api_retrieval.get_session_full(session_id)
        except ValueError as exc:
            raise SessionNotFound(session_id) from exc
        return presentation.assemble_session_dto(full_session, get_settings())
