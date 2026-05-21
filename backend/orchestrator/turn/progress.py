"""
Progress event protocol for streaming turn execution.
Defines the contract the orchestrator uses to notify HTTP-layer callers of
step boundaries while ``run_turn`` drives an async task graph. The
orchestrator invokes a ``ProgressCallback`` at the start and end of each
step; the router translates those callbacks into NDJSON lines on the wire,
which the live-state frontend (``PipelineStatusLine``) renders as the
current stage.

Wire-protocol event shapes (ProgressEvent, ClusterSnapshotEvent, etc.) live
in ``backend.routers.dto.sessions.streaming``.
"""
from typing import Protocol

from backend.routers.dto.sessions.streaming import (
    ClusterSnapshotEvent,
    ProgressEvent,
    ProgressPhase,
    ProgressStep,
)


class ProgressCallback(Protocol):
    """Callable the orchestrator invokes at step boundaries and after clustering.

    Invoked on the event loop thread (``run_turn`` is async). Implementations
    must not block or raise — the orchestrator wraps each invocation
    defensively, but propagating exceptions would still pollute logs.
    """

    def __call__(self, event: ProgressEvent | ClusterSnapshotEvent) -> None:
        """Record a step boundary or cluster snapshot. Must not block or raise."""
        ...


class NullProgressCallback:
    """No-op default used when no streaming client is attached.

    Lets ``run_turn`` keep an unconditional callback invocation in its body
    without forcing every caller (tests, eval scripts, future batch jobs) to
    build a real callback.
    """

    def __call__(self, event: ProgressEvent | ClusterSnapshotEvent) -> None:
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
    "ClusterSnapshotEvent",
    "NullProgressCallback",
    "ProgressCallback",
    "ProgressEvent",
    "ProgressPhase",
    "ProgressStep",
    "make_progress_event",
]
