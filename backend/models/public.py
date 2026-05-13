"""API-facing DTOs for the frontend.

These are explicit public contracts separate from internal types
(ClusterSnapshot, MovieMetadata). Exposed via /routers endpoints only.
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AmbiguityMeta(BaseModel):
    """Metadata for the frontend to render an ask-turn as buttons.

    Attributes:
        ui_format:    Rendering hint — ``"binary"`` for yes/no questions,
                      ``"forced_choice"`` for two-option comparisons.
        cluster_refs: UUIDs of the 2–3 clusters the question targets.
    """

    ui_format: str
    cluster_refs: list[UUID]


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


class ClusterPublic(BaseModel):
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


class MoviePublic(BaseModel):
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


class ConvergedClusterPublic(BaseModel):
    """Payload returned by GET /sessions/{id}/converged-cluster.

    Attributes:
        cluster:            The fine cluster the session converged on.
        movies:             Enriched metadata for each movie in the cluster,
                            in descending score order (top 20).
        preference_profile: Structured oracle preference extracted by the
                            Orchestrator on convergence, or None.
    """

    cluster: ClusterPublic
    movies: list[MoviePublic]
    preference_profile: dict[str, Any] | None
