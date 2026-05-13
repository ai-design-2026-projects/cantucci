"""Result types returned by backend/api/retrieval.py queries."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.models.clusters import ClusterSnapshot
from backend.models.eval import JudgeScore, SessionMetrics


@dataclass
class TurnDetail:
    """Full data for a single completed turn, as returned by get_session_full."""

    id: uuid.UUID
    turn_number: int
    user_message: str
    assistant_message: str | None
    step_type: str | None
    converged: bool
    clusters: list[ClusterSnapshot]
    created_at: datetime


@dataclass
class FeedbackEntry:
    """Oracle feedback record for a single turn."""

    id: uuid.UUID
    turn_id: uuid.UUID
    feedback_level: str
    feedback_type: str
    target_id: str | None
    content: str


@dataclass
class SessionSummary:
    """Lightweight session overview used in run-level aggregates."""

    session_id: uuid.UUID
    run_id: uuid.UUID
    seed: int
    config_hash: str
    model_version: str
    persona_id: str | None
    status: str
    turn_count: int
    converged_at_turn: int | None
    metrics: SessionMetrics | None
    judge_scores: list[JudgeScore]


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
    sessions: list[SessionSummary]
    aggregate: RunAggregate


@dataclass
class SessionFull:
    """Complete session state including all turns, feedback, and eval data."""

    session_id: uuid.UUID
    run_id: uuid.UUID
    seed: int
    config_hash: str
    model_version: str
    persona_id: str | None
    status: str
    preference_profile: dict[str, Any] | None
    turns: list[TurnDetail]
    feedback: list[FeedbackEntry]
    metrics: SessionMetrics | None
    judge_scores: list[JudgeScore]
    created_at: datetime
    updated_at: datetime
    max_turns: int
