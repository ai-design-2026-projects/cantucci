"""
Per-run metric aggregation with 95% confidence intervals.

Pulls raw session_metrics and judge_scores from the DB via backend/api/eval.py
read helpers, then computes bootstrap CIs (continuous) and Wilson score CIs
(proportions) via backend/eval/statistics.py.

No SQL here — all DB access goes through backend/api/eval.
"""

import uuid
from dataclasses import dataclass

from backend.repository.eval import (
    SessionMetricsRead,
    JudgeScoreRead,
    list_judge_scores_for_run,
    list_session_metrics_for_run,
)
from backend.eval.statistics import MetricCI, bootstrap_ci, wilson_ci

JUDGE_DIMENSIONS = ("clustering_coherence", "question_quality", "profile_fidelity")


@dataclass
class MetricBundle:
    """Full suite of per-metric CIs for a cohort of sessions.

    Continuous metrics use bootstrap CIs; proportions use Wilson score CIs.

    Attributes:
        precision_at_k:           Precision@K vs ground-truth film set.
        recall_at_k:              Recall@K vs ground-truth film set.
        ndcg_at_k:                NDCG@K vs ground-truth film set.
        turns_to_convergence:     Turns required to converge (NULL sessions excluded).
        avg_cognitive_load:       Mean cognitive load per turn.
        total_cost_usd:           Total API cost per session (USD).
        drift_events:             Number of preference drift events detected.
        converged_rate:           Proportion of sessions that converged (Wilson).
        explicit_acceptance_rate: Proportion with explicit oracle acceptance (Wilson).
        judge_clustering_coherence: LLM-judge score for cluster coherence.
        judge_question_quality:     LLM-judge score for question quality.
        judge_profile_fidelity:     LLM-judge score for persona fidelity.
    """

    precision_at_k: MetricCI
    recall_at_k: MetricCI
    ndcg_at_k: MetricCI
    turns_to_convergence: MetricCI
    avg_cognitive_load: MetricCI
    total_cost_usd: MetricCI
    drift_events: MetricCI
    converged_rate: MetricCI
    explicit_acceptance_rate: MetricCI
    judge_clustering_coherence: MetricCI
    judge_question_quality: MetricCI
    judge_profile_fidelity: MetricCI


def _compute_bundle(
    metrics: list[SessionMetricsRead],
    judge_scores: list[JudgeScoreRead],
) -> MetricBundle:
    """Compute a MetricBundle from a cohort of session rows.

    Args:
        metrics:      Session-level metric rows for this cohort.
        judge_scores: Judge score rows for this cohort.

    Returns:
        MetricBundle with one MetricCI per metric.
    """
    def _floats(attr: str) -> list[float]:
        return [getattr(m, attr) for m in metrics if getattr(m, attr) is not None]

    def _judge_scores_for(dim: str) -> list[float]:
        return [float(j.score) for j in judge_scores if j.dimension == dim]

    n = len(metrics)

    return MetricBundle(
        precision_at_k=bootstrap_ci(_floats("precision_at_k")),
        recall_at_k=bootstrap_ci(_floats("recall_at_k")),
        ndcg_at_k=bootstrap_ci(_floats("ndcg_at_k")),
        turns_to_convergence=bootstrap_ci(_floats("turns_to_convergence")),
        avg_cognitive_load=bootstrap_ci(_floats("avg_cognitive_load")),
        total_cost_usd=bootstrap_ci([m.total_cost_usd for m in metrics]),
        drift_events=bootstrap_ci([float(m.drift_events) for m in metrics]),
        converged_rate=wilson_ci(sum(1 for m in metrics if m.converged), n),
        explicit_acceptance_rate=wilson_ci(
            sum(1 for m in metrics if m.explicit_acceptance), n
        ),
        judge_clustering_coherence=bootstrap_ci(_judge_scores_for("clustering_coherence")),
        judge_question_quality=bootstrap_ci(_judge_scores_for("question_quality")),
        judge_profile_fidelity=bootstrap_ci(_judge_scores_for("profile_fidelity")),
    )


def aggregate_run(run_id: uuid.UUID) -> MetricBundle:
    """Compute aggregate metrics across all sessions in a run.

    Args:
        run_id: UUID of the run to aggregate.

    Returns:
        MetricBundle for the full run cohort.
    """
    metrics = list_session_metrics_for_run(run_id)
    judge_scores = list_judge_scores_for_run(run_id)
    return _compute_bundle(metrics, judge_scores)


def aggregate_run_by_persona(run_id: uuid.UUID) -> dict[str, MetricBundle]:
    """Compute per-persona aggregate metrics for a run.

    Sessions with persona_id=None are grouped under the key ``"__none__"``.

    Args:
        run_id: UUID of the run to aggregate.

    Returns:
        Dict mapping persona_id (or ``"__none__"``) to its MetricBundle.
    """
    metrics = list_session_metrics_for_run(run_id)
    judge_scores = list_judge_scores_for_run(run_id)

    persona_metrics: dict[str, list[SessionMetricsRead]] = {}
    for m in metrics:
        key = m.persona_id or "__none__"
        persona_metrics.setdefault(key, []).append(m)

    persona_scores: dict[str, list[JudgeScoreRead]] = {}
    for j in judge_scores:
        key = j.persona_id or "__none__"
        persona_scores.setdefault(key, []).append(j)

    return {
        persona: _compute_bundle(
            persona_metrics[persona],
            persona_scores.get(persona, []),
        )
        for persona in persona_metrics
    }
