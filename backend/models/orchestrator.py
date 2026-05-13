"""Orchestrator Protocol — the interface the HTTP router calls."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from backend.models.public import ConvergedClusterPublic, MoviePublic
from backend.models.sessions import SessionState, TurnResult


@dataclass
class OrchestratorRecommendation:
    """Structured output parsed from the Orchestrator's render step.

    The orchestrator's prompt instructs the model to return valid JSON
    matching this shape. ``agent.render_recommendation()`` parses and validates
    the raw string; any mismatch raises ``LLMParseError``.

    Convergence is determined by the Orchestrator's policy (not the LLM).

    Attributes:
        reply: User-facing message presenting the current clusters and
               inviting oracle feedback.
    """

    reply: str


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
