"""Orchestrator Protocol — the interface the HTTP router calls."""

from typing import Protocol
from uuid import UUID

from backend.models.schemas import SessionState, TurnResult


class Orchestrator(Protocol):
    """Interface for orchestrator implementations.

    Concrete implementations live in backend/orchestrator/.
    The HTTP router depends only on this Protocol, never on a concrete class.
    """

    def create_session(self) -> SessionState: ...
    def handle_turn(self, session_id: UUID, user_message: str) -> TurnResult: ...
    def get_session(self, session_id: UUID) -> SessionState: ...
