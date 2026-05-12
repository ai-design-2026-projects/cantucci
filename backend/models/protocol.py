"""Data types shared between the HTTP layer, orchestrator, and (future) data-access layer.

All pydantic models here mirror the ``sessions`` and ``turns`` tables defined in
``docs/specifications/architecture/data_schema.md``.  The ``Orchestrator``
Protocol defines the interface the router calls; concrete implementations live
in ``backend/orchestrator/``.
"""

from datetime import datetime
from enum import Enum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, field_validator


# Enums and pydantic models for the HTTP API and orchestrator protocol.
class SessionStatus(str, Enum):
    """Lifecycle state of a session (maps to the ``status`` column)."""

    active = "active"
    converged = "converged"
    abandoned = "abandoned"

# The StepType enum is used in TurnResult to indicate whether the assistant's
class StepType(str, Enum):
    """Kind of assistant turn (maps to the ``step_type`` column).

    show  — present a recommendation or result.
    ask   — pose a clarifying question.
    stop  — signal that the session should end.
    """

    show = "show"
    ask = "ask"
    stop = "stop"

# Pydantic models for the HTTP API and orchestrator protocol.
class TurnResult(BaseModel):
    """Outcome of a single conversation turn, returned by the orchestrator.

    Attributes:
        turn_id:          UUID of the persisted turn row.
        session_id:       UUID of the owning session.
        turn_number:      1-based index within the session.
        user_message:     The oracle's original message.
        assistant_message: The system's response.
        step_type:        Whether the response shows a result, asks, or stops.
        converged:        True when the session reached a convergence decision.
        created_at:       Server-set UTC timestamp of the turn.
    """

    turn_id: UUID
    session_id: UUID
    turn_number: int
    user_message: str
    assistant_message: str
    step_type: StepType
    converged: bool
    created_at: datetime


class SessionState(BaseModel):
    """Full state of a session including its turn history.

    Attributes:
        session_id:  UUID of the session.
        status:      Current lifecycle state.
        max_turns:   Maximum number of turns before forced termination.
        created_at:  Server-set UTC timestamp of session creation.
        updated_at:  Server-set UTC timestamp of the last state change.
        turns:       Ordered list of all turns (ascending turn_number).
    """

    session_id: UUID
    status: SessionStatus
    max_turns: int
    created_at: datetime
    updated_at: datetime
    turns: list[TurnResult]


class TurnRequest(BaseModel):
    """HTTP request body for POST /sessions/{session_id}/turns.

    Attributes:
        user_message: The oracle's message for this turn. Must be non-empty.
    """

    user_message: str

    @field_validator("user_message")
    @classmethod
    def non_empty(cls, v: str) -> str:
        """Reject blank or whitespace-only messages at the HTTP boundary.

        Args:
            v: The raw user_message value from the request body.

        Returns:
            The validated, untrimmed value.

        Raises:
            ValueError: If the string is empty or contains only whitespace.
        """
        if not v.strip():
            raise ValueError("user_message must not be empty or whitespace")
        return v


# Exceptions raised by the orchestrator and handled by the HTTP layer to return appropriate status codes.
class SessionNotFound(Exception):
    """Raised by the orchestrator when a session_id does not exist.

    The HTTP layer catches this and returns 404.

    Attributes:
        session_id: The UUID that was looked up and not found.
    """

    def __init__(self, session_id: UUID) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id} not found")


