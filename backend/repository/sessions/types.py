from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.cluster.domain import ClusterAssignment, ClusterSpecification
from backend.repository.eval.types import JudgeScoreRow, SessionMetricsRow


@dataclass
class ClusterRow:
    """DB-shaped cluster state for one turn, read back from the clusters table."""
    id: uuid.UUID
    name: str
    description: str | None
    level: int
    parent_cluster_id: uuid.UUID | None
    assignments: list[ClusterAssignment]

    def to_spec(self) -> ClusterSpecification:
        """Convert the snapshot back to a Specification for insertion."""
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
class FeedbackRow:
    """Oracle feedback record for a single turn."""
    id: uuid.UUID
    turn_id: uuid.UUID
    feedback_level: str
    feedback_type: str
    target_id: str | None
    content: str


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
class SessionListRow:
    """Lightweight projection of a session row for history listings.
    Attributes:
        session_id:         Session UUID.
        run_id:             UUID of the parent run.
        seed:               Per-session RNG seed.
        config_hash:        SHA-256 prefix of the YAML config snapshot.
        model_version:      LLM model identifier used for this session.
        status:             Lifecycle state (active | converged | abandoned).
        created_at:         UTC timestamp of session creation.
        updated_at:         UTC timestamp of the last state change.
        turn_count:         Number of completed turns in this session.
        first_user_message: Text of the first oracle message, or None for
                            sessions with no turns yet.
        cluster_snapshot:   Current cluster state (latest clustered turn's
                            clusters). Empty list when no clustered turn yet.
    """
    session_id: uuid.UUID
    run_id: uuid.UUID
    seed: int
    config_hash: str
    model_version: str
    status: str
    created_at: datetime
    updated_at: datetime
    turn_count: int
    first_user_message: str | None
    cluster_snapshot: list[ClusterRow] = field(default_factory=list)


@dataclass
class SessionRow:
    """Complete internal session state: turns, clusters, feedback, metrics.
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
