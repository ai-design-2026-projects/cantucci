"""Types for evaluation results (session_metrics and judge_scores tables)."""

import uuid
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class SessionMetrics:
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
class JudgeScore:
    id: uuid.UUID
    dimension: str
    score: int
    rationale: str | None
    judge_model: str
    judge_prompt_hash: str
