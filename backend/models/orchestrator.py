"""Orchestrator Protocol — the interface the HTTP router calls."""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from backend.models.public import ConvergedClusterPublic, MoviePublic
from backend.models.sessions import SessionState, TurnResult


@dataclass
class OrchestratorTurnResponse:
    """Structured output parsed from the Orchestrator LLM call.

    The orchestrator's prompt instructs the model to return valid JSON
    matching this shape.  ``agent.respond()`` parses and validates the raw
    string; any mismatch raises ``LLMParseError``.

    Attributes:
        reply:              User-facing assistant text.
        converged:          True when the LLM judges preferences sufficiently
                            clear to terminate the session.
        preference_profile: Structured profile extracted from oracle feedback.
                            Must be non-None when ``converged=True``.
    """

    reply: str
    converged: bool
    preference_profile: dict[str, Any] | None


class Orchestrator(Protocol):
    """Interface for orchestrator implementations.

    Concrete implementations live in backend/orchestrator/.
    The HTTP router depends only on this Protocol, never on a concrete class.
    """

    def create_session(self) -> SessionState: ...
    def handle_turn(self, session_id: UUID, user_message: str) -> TurnResult: ...
    def get_session(self, session_id: UUID) -> SessionState: ...
    def get_converged_cluster(self, session_id: UUID) -> ConvergedClusterPublic: ...
    def get_movie(self, movie_id: int) -> MoviePublic: ...
