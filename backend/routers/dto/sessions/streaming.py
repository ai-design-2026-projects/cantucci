from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Union

from pydantic import BaseModel, Field

from backend.routers.dto.sessions.dtos import TurnDto


class ProgressStep(str, Enum):
    """
    Pipeline checkpoints a streaming client may observe, from coarse wave-level
    to fine sub-step. Coarse values (UNDERSTAND, CHOOSE, FINALIZE, WRAP_UP) are
    kept for back-compat; fine-grained values are emitted in addition so clients
    can display a more specific status label.

    Wave-level:
    * ``UNDERSTAND`` — Wave 1: parallel state gate + profile + retrieval +
                       clustering. Sub-steps RETRIEVING and CLUSTERING fire
                       within this wave.
    * ``CHOOSE``     — Wave 2: decision agent selects ask or show. Sub-steps
                       DECIDING and COMPOSING fire within this wave.
    * ``FINALIZE``   — Reply persistence and profile update.
    * ``WRAP_UP``    — Early-exit paths (hard limit, natural end, drift, empty
                       retrieval) that bypass the main pipeline.

    Fine-grained sub-steps (fired in addition to the wave event):
    * ``RETRIEVING`` — Vector search running inside UNDERSTAND.
    * ``CLUSTERING`` — Cluster refinement running inside UNDERSTAND, after
                       retrieval results are ready.
    * ``DECIDING``   — Decision agent running inside CHOOSE.
    * ``COMPOSING``  — Reply text being built inside CHOOSE.
    """
    UNDERSTAND = "understand"
    RETRIEVING = "retrieving"
    CLUSTERING = "clustering"
    CHOOSE = "choose"
    DECIDING = "deciding"
    COMPOSING = "composing"
    FINALIZE = "finalize"
    WRAP_UP = "wrap_up"


ProgressPhase = Literal["start", "end"]


class ProgressEvent(BaseModel):
    """
    One step boundary in a turn.

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
    """
    Lightweight film metadata carried in a cluster snapshot event.
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
    """
    One cluster as it appears in a mid-turn snapshot event.
    Attributes:
        id:          Cluster UUID (string form).
        name:        Human-readable cluster label.
        description: Short theme description or None.
        level:       1 = coarse, 2 = fine.
        confidence:  Mean soft-assignment score over non-excluded films in [0, 1].
        films:       All assigned films: non-excluded first (score desc), then
                     excluded. Matches the ordering used in ClusterDto.top_titles.
    """
    id: str
    name: str
    description: str | None
    level: int
    confidence: float
    films: list[ClusterFilmStub]


class ClusterSnapshotEvent(BaseModel):
    """
    Mid-turn event carrying the live cluster snapshot after clustering.
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
    """
    Terminal event carrying the full turn payload.
    Attributes:
        type: Always ``"result"`` for discrimination.
        data: The same ``TurnDto`` shape the legacy JSON endpoint returned.
    """
    type: Literal["result"] = "result"
    data: TurnDto


class ErrorEvent(BaseModel):
    """
    Terminal event emitted when the worker thread raises.
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


__all__ = [
    "ClusterFilmStub",
    "ClusterSnapshotEvent",
    "ClusterSnapshotPayload",
    "ErrorEvent",
    "ProgressEvent",
    "ProgressPhase",
    "ProgressStep",
    "ResultEvent",
    "StreamEvent",
]
