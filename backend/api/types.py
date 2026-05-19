"""
Shared types for the api/ data-access layer.
Covers DB-facing domain objects (cluster rows, movie rows, session metrics,
turn rows) and the DB-column enums (SessionStatus, StepType).  These are the
types that cross the api/ boundary — every other layer imports them from here.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel


@dataclass
class MovieHit:
    """A single vector-search result before metadata enrichment."""
    movie_id: int
    title: str
    score: float  # cosine similarity in [0, 1]; higher is more relevant


@dataclass
class MovieRow:
    """Enriched film metadata returned by the Retriever and stored in the movies table."""
    movie_id: int
    title: str
    overview: str | None
    tagline: str | None
    release_year: int | None
    genres: list[str] = field(default_factory=list)
    director: str | None = None


@dataclass
class ClusterSpecification:
    """Input spec for snapshot_clusters: one item per cluster to insert."""
    name: str
    description: str | None
    level: int
    centroid: list[float] | None
    parent_cluster_id: uuid.UUID | None
    # List of (movie_id, score, excluded) tuples
    assignments: list[tuple[int, float, bool]]


@dataclass
class ClusterAssignment:
    """Soft-cluster membership score for a single film."""
    movie_id: int
    score: float
    excluded: bool
    title: str | None = None


@dataclass
class ClusterRow:
    """In-memory cluster state for one turn — never written directly to DB."""
    id: uuid.UUID
    name: str
    description: str | None
    level: int
    parent_cluster_id: uuid.UUID | None
    assignments: list[ClusterAssignment]

    def to_spec(self) -> ClusterSpecification:
        """Convert the snapshot back to a Specification for insertion"""
        return ClusterSpecification(
            name=self.name,
            description=self.description,
            level=self.level,
            centroid=None,
            parent_cluster_id=self.parent_cluster_id,
            assignments=[
                (a.movie_id, a.score, a.excluded) for a in self.assignments
            ],
        )


@dataclass
class SessionMetricsRow:
    """Aggregate quality metrics for a completed session."""
    session_id: uuid.UUID
    converged: bool
    turns_to_convergence: int | None
    avg_cognitive_load: float | None
    explicit_acceptance: bool
    drift_events: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: Decimal


@dataclass
class JudgeScoreRow:
    """LLM-as-judge score for a single evaluation dimension."""
    id: uuid.UUID
    dimension: str
    score: int
    rationale: str | None
    judge_model: str
    judge_prompt_hash: str



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


@dataclass
class TurnRow:
    """Full data for a single completed turn, as returned by get_session_full."""

    id: uuid.UUID
    turn_number: int
    user_message: str
    assistant_message: str | None
    step_type: str | None
    converged: bool
    clusters: list[ClusterRow]
    created_at: datetime


@dataclass
class FeedbackRow:
    """Oracle feedback record for a single turn."""

    id: uuid.UUID
    turn_id: uuid.UUID
    feedback_level: str
    feedback_type: str
    target_id: str | None
    content: str


@dataclass
class SessionSummaryRow:
    """Lightweight session overview used in run-level aggregates."""

    session_id: uuid.UUID
    run_id: uuid.UUID
    seed: int
    config_hash: str
    model_version: str
    status: str
    turn_count: int
    converged_at_turn: int | None
    metrics: SessionMetricsRow | None
    judge_scores: list[JudgeScoreRow]


@dataclass
class RunAggregate:
    """Computed statistics across all sessions in a run."""

    n_sessions: int
    convergence_rate: float
    mean_turns_to_convergence: float | None
    mean_cognitive_load: float | None
    mean_judge: dict[str, float]


@dataclass
class RunResults:
    """Full results for a run: all session summaries plus aggregate stats."""

    run_id: uuid.UUID
    sessions: list[SessionSummaryRow]
    aggregate: RunAggregate


@dataclass
class SessionRow:
    """Complete internal session state: turns, clusters, feedback, metrics.

    This is the read-side type used by the orchestrator and all internal
    agents. It is never serialised directly; the HTTP layer converts it to
    ``SessionDto`` via ``presentation.assemble_session_dto``.

    Attributes:
        session_id:         Session UUID.
        run_id:             UUID of the parent run.
        seed:               Per-session RNG seed.
        config_hash:        SHA-256 prefix of the YAML config snapshot.
        model_version:      LLM model identifier used for this session.
        status:             Lifecycle state (active | converged | abandoned).
        preference_profile: Structured oracle preference from the last turn.
        turns:              Ordered list of completed turns.
        cluster_snapshot:   Clusters from the most recent clustered turn.
                            Mirrors the ``clusters.session_id`` FK at the
                            in-memory level so agents can read current state
                            without walking all turns.
        feedback:           All oracle feedback records for this session.
        metrics:            Aggregate quality metrics, or None if unavailable.
        judge_scores:       LLM-as-judge scores.
        created_at:         UTC timestamp of session creation.
        updated_at:         UTC timestamp of the last state change.
        max_turns:          Hard turn budget for this session.
    """

    session_id: uuid.UUID
    run_id: uuid.UUID
    seed: int
    config_hash: str
    model_version: str
    status: str
    preference_profile: dict[str, Any] | None
    turns: list[TurnRow]
    cluster_snapshot: list[ClusterRow]
    feedback: list[FeedbackRow]
    metrics: SessionMetricsRow | None
    judge_scores: list[JudgeScoreRow]
    created_at: datetime
    updated_at: datetime
    max_turns: int


class Run(BaseModel):
    """In-memory representation of a runs row."""

    id: uuid.UUID
    name: str
    condition: str
    config_hash: str
    config_snapshot: dict[str, Any]
    seed: int
    model_version: str
    status: str
    notes: str | None
