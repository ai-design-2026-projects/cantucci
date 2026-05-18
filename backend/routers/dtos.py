"""
HTTP-boundary DataTransferObjects for the frontend.

Pydantic models used exclusively at the HTTP layer: request bodies, response
payloads, and per-field metadata needed for frontend rendering.  All internal
types (ClusterRow, MovieRow, etc.) are separate — see backend/api/types.py.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_validator

from backend.api.types import SessionStatus, StepType


class AmbiguityMeta(BaseModel):
    """Metadata for the frontend to render an ask-turn as buttons.

    Attributes:
        ui_format:    Rendering hint — ``"binary"`` for yes/no questions,
                      ``"forced_choice"`` for two-option comparisons.
        cluster_refs: UUIDs of the 2–3 clusters the question targets.
    """

    ui_format: str
    cluster_refs: list[UUID]


class TurnDto(BaseModel):
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
        recommendation:   Structured cluster + films payload for show/stop turns.
    """

    turn_id: UUID
    session_id: UUID
    turn_number: int
    user_message: str
    assistant_message: str
    step_type: StepType
    converged: bool
    created_at: datetime
    ambiguity_meta: AmbiguityMeta | None = None
    recommendation: "RecommendationDto | None" = None


class SessionDto(BaseModel):
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
    turns: list[TurnDto]


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



class SoftScore(BaseModel):
    """Soft assignment score for one movie in a cluster.

    Attributes:
        movie_id:  TMDB movie id.
        score:     Confidence in [0, 1] that this movie belongs to the cluster.
        excluded:  True if the oracle explicitly excluded this movie.
    """

    movie_id: int
    score: float
    excluded: bool


class ClusterDto(BaseModel):
    """A single cluster as exposed to the frontend.

    Attributes:
        id:                Cluster UUID.
        name:              Human-readable cluster label.
        description:       Short description of the cluster's theme.
        level:             1 = coarse, 2 = fine.
        parent_cluster_id: UUID of the parent coarse cluster, or None.
        soft_scores:       Per-movie soft assignment scores.
        top_titles:        Movie ids sorted by descending score (top ~5).
    """

    id: UUID
    name: str
    description: str | None
    level: int
    parent_cluster_id: UUID | None
    soft_scores: list[SoftScore]
    top_titles: list[int]


class MovieDto(BaseModel):
    """Full movie metadata as exposed to the frontend.

    Attributes:
        id:                TMDB movie id.
        title:             English release title.
        release_year:      4-digit year, or None.
        runtime:           Duration in minutes, or None.
        vote_average:      TMDB mean rating 0–10.
        vote_count:        Number of TMDB votes.
        bayesian_rating:   Bayesian-smoothed rating (preferred ranking signal).
        overview:          Plot synopsis.
        poster_url:        Full TMDB poster URL (``https://image.tmdb.org/t/p/w500{path}``),
                           or None when ``poster_path`` is absent.
        genres:            List of genre names.
        director:          Director name, or None.
        top_cast:          Up to 3 top-billed cast names.
        original_language: ISO 639-1 language code.
    """

    id: int
    title: str
    release_year: int | None
    runtime: float | None
    vote_average: float | None
    vote_count: int | None
    bayesian_rating: float | None
    overview: str | None
    poster_url: str | None
    genres: list[str]
    director: str | None
    top_cast: list[str]
    original_language: str | None


class RecommendationDto(BaseModel):
    """Structured recommendation payload emitted on show and stop turns.

    Attributes:
        cluster: The cluster selected as best match by the Decision Agent.
        films:   Top-K films in descending score order, fully enriched.
    """

    cluster: ClusterDto
    films: list[MovieDto]


class ConvergedClusterDto(BaseModel):
    """Payload returned by GET /sessions/{id}/converged-cluster.

    Attributes:
        cluster:            The fine cluster the session converged on.
        movies:             Enriched metadata for each movie in the cluster,
                            in descending score order (top 20).
        preference_profile: Structured oracle preference extracted by the
                            Orchestrator on convergence, or None.
    """

    cluster: ClusterDto
    movies: list[MovieDto]
    preference_profile: dict[str, Any] | None


TurnDto.model_rebuild()
