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

from backend.orchestrator.domain import SessionStatus, StepType


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
    """HTTP representation of a session, used by both the listing and detail endpoints.

    Public fields (serialized to the frontend):
        session_id, status, max_turns, created_at, updated_at,
        turn_count, first_user_message, cluster_snapshot, turns.

    Attributes:
        session_id:          UUID of the session.
        status:              Current lifecycle state.
        max_turns:           Maximum number of turns before forced termination.
        created_at:          Server-set UTC timestamp of session creation.
        updated_at:          Server-set UTC timestamp of the last state change.
        turn_count:          Number of completed turns (populated on both endpoints).
        first_user_message:  Text of the first oracle message, or None.
        cluster_snapshot:    Current cluster state (latest clustered turn's clusters).
        turns:               Ordered list of all turns; empty on the listing endpoint.
    """

    session_id: UUID
    status: SessionStatus
    max_turns: int
    created_at: datetime
    updated_at: datetime
    turn_count: int = 0
    first_user_message: str | None = None
    cluster_snapshot: list["ClusterDto"] = []
    turns: list[TurnDto] = []

    def converged_turn(self) -> "TurnDto | None":
        """Return the turn where convergence was declared, or None.

        Returns:
            The ``TurnDto`` with ``converged=True``, or ``None`` if none exist.
        """
        for turn in reversed(self.turns):
            if turn.converged:
                return turn
        return None

    def last_turn_with_recommendation(self) -> "TurnDto | None":
        """Return the last turn carrying a non-None recommendation, or None.

        Returns:
            ``TurnDto`` with a recommendation, or ``None``.
        """
        for turn in reversed(self.turns):
            if turn.recommendation is not None:
                return turn
        return None

    def transcript(self) -> str:
        """Build a plain-text turn-by-turn transcript.

        Returns:
            Multi-line string with alternating Oracle / CinePal lines.
        """
        lines: list[str] = []
        for turn in self.turns:
            lines.append(f"[Turn {turn.turn_number}]")
            lines.append(f"Oracle: {turn.user_message}")
            lines.append(f"CinePal: {turn.assistant_message}")
            lines.append("")
        return "\n".join(lines)


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
        top_titles:        All assigned film ids: non-excluded first (score desc), then excluded.
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


class MetricCIDto(BaseModel):
    """Point estimate and 95% confidence interval for a single metric.

    Attributes:
        value: Point estimate (mean or proportion).
        ci_lo: Lower CI bound.
        ci_hi: Upper CI bound.
        n:     Sample size.
    """

    value: float
    ci_lo: float
    ci_hi: float
    n: int


class MetricBundleDto(BaseModel):
    """Full suite of per-metric CIs for a run cohort.

    Continuous metrics use bootstrap CIs; binary proportions use Wilson score CIs.
    """

    precision_at_k: MetricCIDto
    recall_at_k: MetricCIDto
    ndcg_at_k: MetricCIDto
    turns_to_convergence: MetricCIDto
    avg_cognitive_load: MetricCIDto
    total_cost_usd: MetricCIDto
    drift_events: MetricCIDto
    converged_rate: MetricCIDto
    explicit_acceptance_rate: MetricCIDto
    judge_clustering_coherence: MetricCIDto
    judge_question_quality: MetricCIDto
    judge_profile_fidelity: MetricCIDto


class RunSummaryDto(BaseModel):
    """Lightweight run summary for the run listing endpoint.

    Attributes:
        id:          Run UUID.
        name:        Human-readable run label.
        condition:   Experimental condition.
        status:      Lifecycle status (running | completed | aborted).
        started_at:  UTC timestamp of run creation.
        ended_at:    UTC timestamp of finalization, or None if still running.
        n_sessions:  Total number of sessions in this run.
    """

    id: UUID
    name: str
    condition: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    n_sessions: int


class RunDetailDto(BaseModel):
    """Full run metadata with overall aggregate metrics.

    Attributes:
        id:            Run UUID.
        name:          Human-readable run label.
        condition:     Experimental condition.
        config_hash:   SHA-256 prefix of the YAML config snapshot.
        seed:          RNG seed shared across all sessions.
        model_version: LLM model identifier.
        status:        Lifecycle status.
        notes:         Optional free-text annotation.
        started_at:    UTC timestamp of run creation.
        ended_at:      UTC timestamp of finalization, or None.
        n_sessions:    Total number of sessions in this run.
        aggregate:     Overall per-metric CIs across all sessions.
    """

    id: UUID
    name: str
    condition: str
    config_hash: str
    seed: int
    model_version: str
    status: str
    notes: str | None
    started_at: datetime | None
    ended_at: datetime | None
    n_sessions: int
    aggregate: MetricBundleDto


class EvalSessionRowDto(BaseModel):
    """Per-session eval metrics for the drill-down table endpoint.

    Attributes:
        session_id:                  Session UUID.
        persona_id:                  Eval persona slug, or None for live sessions.
        ground_truth_id:             Ground-truth set slug, or None for live sessions.
        converged:                   Whether the session reached convergence.
        explicit_acceptance:         Whether convergence was triggered by explicit oracle signal.
        turns_to_convergence:        Turn number when convergence was declared, or None.
        avg_cognitive_load:          Mean cognitive load per turn, or None.
        total_cost_usd:              Total API cost in USD.
        drift_events:                Count of preference drift events.
        precision_at_k:              Precision@K vs ground-truth, or None.
        recall_at_k:                 Recall@K vs ground-truth, or None.
        ndcg_at_k:                   NDCG@K vs ground-truth, or None.
        judge_clustering_coherence:  Judge score 1–5, or None.
        judge_question_quality:      Judge score 1–5, or None.
        judge_profile_fidelity:      Judge score 1–5, or None.
    """

    session_id: UUID
    persona_id: str | None
    ground_truth_id: str | None
    converged: bool
    explicit_acceptance: bool
    turns_to_convergence: int | None
    avg_cognitive_load: float | None
    total_cost_usd: float
    drift_events: int
    precision_at_k: float | None
    recall_at_k: float | None
    ndcg_at_k: float | None
    judge_clustering_coherence: int | None
    judge_question_quality: int | None
    judge_profile_fidelity: int | None


TurnDto.model_rebuild()
SessionDto.model_rebuild()
