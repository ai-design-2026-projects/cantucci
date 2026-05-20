import uuid
from dataclasses import dataclass
from decimal import Decimal


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
    precision_at_k: float | None = None
    recall_at_k: float | None = None
    ndcg_at_k: float | None = None


@dataclass
class JudgeScoreRow:
    """LLM-as-judge score for a single evaluation dimension."""
    id: uuid.UUID
    session_id: uuid.UUID
    dimension: str
    score: int
    rationale: str | None
    judge_model: str
    judge_prompt_hash: str


@dataclass
class SessionMetricsRead:
    """JOIN projection of session_metrics + sessions fields needed for aggregation."""
    session_id: uuid.UUID
    persona_id: str | None
    ground_truth_id: str | None
    converged: bool
    turns_to_convergence: int | None
    avg_cognitive_load: float | None
    explicit_acceptance: bool
    drift_events: int
    total_cost_usd: float
    precision_at_k: float | None
    recall_at_k: float | None
    ndcg_at_k: float | None


@dataclass
class JudgeScoreRead:
    """Minimal judge_scores projection for aggregation — dimension + score per session."""
    session_id: uuid.UUID
    persona_id: str | None
    dimension: str
    score: int
