"""Progress event protocol for streaming turn execution.

Defines the contract the orchestrator uses to notify HTTP-layer callers of
step boundaries while ``run_turn`` drives an async task graph. The
orchestrator invokes a ``ProgressCallback`` at the start and end of each
step; the router translates those callbacks into NDJSON lines on the wire,
which the live-state frontend (``PipelineStatusLine``) renders as the
current stage.

This module owns the callback shape and the event payloads, so the router
never reaches into orchestrator internals to invent event types.

Parallel components
-------------------
The ``understand`` step wraps the parallel front of the per-turn task
graph. After a synchronous hard-limit check, the orchestrator schedules
the following as concurrent ``asyncio.Task``s:

* ``state_agent.check_gate``  — LLM drift / end / re-retrieve gate.
* ``profile_agent.extract``   — preference-profile extraction.
* one speculative branch — ``cluster_agent.refine`` whenever the session
  already has clusters from a prior turn (whether the prior assistant
  message was an ``ask`` or a ``show``), OR
  ``retrieval_agent.retrieve_from_message → cluster_agent.describe_clusters``
  on the truly-first clustered turn of the session.

Retrieval is reserved for three precise moments: the first clustered
turn of a session, ``drift_confirmed`` (cancel speculative, then
``retrieve_from_profile``), and ``re_retrieve`` (same, with seen films
excluded). Every other turn evolves the cluster set in place via
refinement. The state gate runs concurrently with the speculative
branch; cancellation propagates as ``asyncio.CancelledError`` through
the async LLM harness, closing the in-flight ``httpx`` connection
whenever the gate's verdict invalidates the speculation.

The ``choose`` step wraps the post-gate decision, which is a single
serial call to ``decision_agent.decide`` (ambiguity was merged into the
decision agent in PR #61, so there is no longer a second parallel sibling
here).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Protocol, Union

from pydantic import BaseModel, Field

from backend.routers.dtos import TurnResult


class ProgressStep(str, Enum):
    """The wave-level checkpoints a streaming client may observe.

    Orchestrator v2 runs Wave 1 as three agents in parallel and Wave 2 as a
    single serial agent, so per-agent boundaries would either fire
    concurrently or lie about ordering. Each value here wraps one logical
    block the user perceives as a single activity:

    * ``understand`` — Wave 1, parallel: state + profile + refine (if
                       applicable). Retrieval runs serially after state check
                       on fresh turns.
    * ``choose``     — Wave 2, serial: decision (now generates the
      clarifying question itself; ambiguity merged in per PR #61).
    * ``finalize``   — Reply rendering and final persistence.
    * ``wrap_up``    — Early-exit paths (hard limit, natural end, drift,
      empty retrieval) that skip the rest of the pipeline.
    """

    understand = "understand"
    choose = "choose"
    finalize = "finalize"
    wrap_up = "wrap_up"


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


class ClusterFilmStub(BaseModel):
    """Lightweight film metadata carried in a cluster snapshot event.

    Attributes:
        id:            TMDB movie id.
        title:         English release title.
        poster_url:    Full TMDB poster URL or None.
        release_year:  4-digit release year or None.
        vote_average:  TMDB mean rating 0–10 or None.
    """

    id: int
    title: str
    poster_url: str | None
    release_year: int | None
    vote_average: float | None


class ClusterSnapshotPayload(BaseModel):
    """One cluster as it appears in a mid-turn snapshot event.

    Attributes:
        id:          Cluster UUID (string form).
        name:        Human-readable cluster label.
        description: Short theme description or None.
        level:       1 = coarse, 2 = fine.
        top_films:   Top-K films sorted by descending soft score.
    """

    id: str
    name: str
    description: str | None
    level: int
    top_films: list[ClusterFilmStub]


class ClusterSnapshotEvent(BaseModel):
    """Mid-turn event carrying the live cluster snapshot after clustering.

    Emitted once per turn, after Wave 1 clustering completes, so the frontend
    can update the Cluster Snapshot panel in real time while the decision
    agent is still running.

    Attributes:
        type:     Always ``"clusters"`` for discrimination.
        clusters: List of cluster payloads, ordered by cluster level then name.
        ts:       Server-set UTC timestamp.
    """

    type: Literal["clusters"] = "clusters"
    clusters: list[ClusterSnapshotPayload]
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


StreamEvent = Union[ProgressEvent, ClusterSnapshotEvent, ResultEvent, ErrorEvent]
"""Discriminated union of everything that can appear on the wire."""


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
    "ClusterFilmStub",
    "ClusterSnapshotEvent",
    "ClusterSnapshotPayload",
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
