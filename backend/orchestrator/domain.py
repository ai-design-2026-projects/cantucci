"""Domain enumerations owned by the orchestrator.

These are business vocabulary produced by the orchestrator turn pipeline and
consumed across the orchestrator, state agent, and HTTP layer. They are NOT
DB-specific — they happen to be persisted as column values, but their meaning
belongs to the domain, not the repository.
"""
from enum import Enum


class SessionStatus(str, Enum):
    """Lifecycle state of a session (maps to the ``status`` column)."""
    active = "active"
    converged = "converged"
    abandoned = "abandoned"


class StepType(str, Enum):
    """Kind of assistant turn (maps to the ``step_type`` column).

    show  — present a recommendation or result.
    ask   — pose a clarifying question.
    stop  — signal that the session should end.
    """

    show = "show"
    ask = "ask"
    stop = "stop"
