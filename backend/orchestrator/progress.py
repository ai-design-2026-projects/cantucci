"""Progress event protocol for streaming turn execution.

Defines the contract the orchestrator uses to notify HTTP-layer callers of
step boundaries while ``handle_turn`` runs synchronously. The orchestrator
invokes a ``ProgressCallback`` at the start and end of each agent step; the
router translates those callbacks into NDJSON lines on the wire.

This module owns the callback shape and the event payloads, so the router
never reaches into orchestrator internals to invent event types.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Protocol, Union

from pydantic import BaseModel, Field

from backend.routers.dtos import TurnResult


class ProgressStep(str, Enum):
    """The agent steps a streaming client may observe.

    Values mirror the natural blocks inside ``Orchestrator.handle_turn``:
    retrieval, clustering, decision, then either ambiguity (continue) or
    render (stop), then persist.
    """

    retrieval = "retrieval"
    cluster = "cluster"
    decision = "decision"
    ambiguity = "ambiguity"
    render = "render"
    persist = "persist"


ProgressPhase = Literal["start", "end"]


class ProgressEvent(BaseModel):
    """One step boundary in a turn.

    Attributes:
        type: Always ``"progress"`` so frontend can discriminate the union.
        step: Which orchestrator step the boundary refers to.
        phase: ``"start"`` when the step begins, ``"end"`` when it returns.
        ts:   Server-set UTC timestamp of the boundary.
    """

    type: Literal["progress"] = "progress"
    step: ProgressStep
    phase: ProgressPhase
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResultEvent(BaseModel):
    """Terminal event carrying the full turn payload.

    Attributes:
        type: Always ``"result"`` for discrimination.
        data: The same ``TurnResult`` shape the legacy JSON endpoint returned.
    """

    type: Literal["result"] = "result"
    data: TurnResult


class ErrorEvent(BaseModel):
    """Terminal event emitted when the worker thread raises.

    HTTP status is already 200 by the time we know about the failure (headers
    are flushed before the orchestrator runs), so the frontend learns about
    errors by seeing this line instead of a ``result`` line.

    Attributes:
        type:    Always ``"error"`` for discrimination.
        code:    Short machine-readable code (e.g. exception class name).
        message: Human-readable failure reason; safe to surface in the UI.
    """

    type: Literal["error"] = "error"
    code: str
    message: str


StreamEvent = Union[ProgressEvent, ResultEvent, ErrorEvent]
"""Discriminated union of everything that can appear on the wire."""


class ProgressCallback(Protocol):
    """Callable the orchestrator invokes at each step boundary.

    Implementations must be thread-safe: ``handle_turn`` may be running in a
    worker thread while the FastAPI event loop consumes events on another.
    Implementations must not raise — the orchestrator wraps each invocation
    defensively, but propagating exceptions would still pollute logs.
    """

    def __call__(self, event: ProgressEvent) -> None:
        """Record a step boundary. Must not block on I/O and must not raise."""
        ...


class NullProgressCallback:
    """No-op default used when no streaming client is attached.

    Lets ``handle_turn`` keep an unconditional callback invocation in its body
    without forcing every caller (tests, eval scripts, future batch jobs) to
    build a real callback.
    """

    def __call__(self, event: ProgressEvent) -> None:
        """Discard the event."""
        return None


def make_progress_event(step: ProgressStep, phase: ProgressPhase) -> ProgressEvent:
    """Convenience constructor used by the router-side callback.

    Args:
        step:  The orchestrator step whose boundary we are recording.
        phase: ``"start"`` or ``"end"``.

    Returns:
        A ``ProgressEvent`` with a server-set UTC timestamp.
    """
    return ProgressEvent(step=step, phase=phase)


__all__ = [
    "ErrorEvent",
    "NullProgressCallback",
    "ProgressCallback",
    "ProgressEvent",
    "ProgressPhase",
    "ProgressStep",
    "ResultEvent",
    "StreamEvent",
    "make_progress_event",
]
