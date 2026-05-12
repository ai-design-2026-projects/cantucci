"""EchoOrchestrator — placeholder implementation of the Orchestrator protocol.

Satisfies ``backend.models.protocol.Orchestrator`` without a database or LLM.
All session state is held in an instance-level dict so there is no module-level
cache and no cross-session leakage.  Timestamps are always server-set in UTC.

Replacement path: when the real orchestrator is ready, replace the body of this
file (keeping the class name and import path stable) and update the single
construction site in ``backend/app.py``.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.models.protocol import (
    SessionNotFound,
    SessionState,
    SessionStatus,
    StepType,
    TurnResult,
)

log = logging.getLogger(__name__)


class EchoOrchestrator:
    """Stub orchestrator: creates sessions and echoes every user message back.

    State is stored in ``self._sessions`` — never at module scope — so multiple
    instances are isolated and tests can construct fresh instances freely.
    """

    def __init__(self) -> None:
        # Keyed by session UUID; values are mutated in place by handle_turn.
        self._sessions: dict[UUID, SessionState] = {}

    def create_session(self) -> SessionState:
        """Allocate a new active session with an empty turn list.

        Returns:
            A ``SessionState`` with status=active and server-set UTC timestamps.
        """
        now = datetime.now(timezone.utc)
        state = SessionState(
            session_id=uuid4(),
            status=SessionStatus.active,
            max_turns=15,
            created_at=now,
            updated_at=now,
            turns=[],
        )
        self._sessions[state.session_id] = state
        log.debug("session created", extra={"session_id": str(state.session_id)})
        return state

    def handle_turn(self, session_id: UUID, user_message: str) -> TurnResult:
        """Append a turn whose assistant_message mirrors user_message (echo).

        Args:
            session_id:   UUID of the target session.
            user_message: The oracle's message.

        Returns:
            A ``TurnResult`` with assistant_message==user_message and
            step_type=show, converged=False.

        Raises:
            SessionNotFound: If *session_id* is not in this instance's store.
        """
        state = self._get_or_raise(session_id)
        now = datetime.now(timezone.utc)
        turn = TurnResult(
            turn_id=uuid4(),
            session_id=session_id,
            turn_number=len(state.turns) + 1,
            user_message=user_message,
            assistant_message=user_message,  # echo
            step_type=StepType.show,
            converged=False,
            created_at=now,
        )
        state.turns.append(turn)
        state.updated_at = now
        log.debug(
            "turn handled",
            extra={"session_id": str(session_id), "turn_number": turn.turn_number},
        )
        return turn

    def get_session(self, session_id: UUID) -> SessionState:
        """Return the full state of a session including its turn history.

        Args:
            session_id: UUID of the session to look up.

        Returns:
            The ``SessionState`` with all turns in ascending turn_number order.

        Raises:
            SessionNotFound: If *session_id* is not in this instance's store.
        """
        return self._get_or_raise(session_id)

    def _get_or_raise(self, session_id: UUID) -> SessionState:
        """Look up a session or raise SessionNotFound — never return None silently.

        Args:
            session_id: The UUID to look up.

        Returns:
            The ``SessionState`` for that session.

        Raises:
            SessionNotFound: If the session does not exist.
        """
        state = self._sessions.get(session_id)
        if state is None:
            raise SessionNotFound(session_id)
        return state
