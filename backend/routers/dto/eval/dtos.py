from uuid import UUID
from pydantic import BaseModel


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
