from backend.eval.aggregator import MetricBundle
from backend.eval.statistics import MetricCI
from backend.routers.dto.eval.dtos import MetricBundleDto, MetricCIDto


def metric_ci_dto(ci: MetricCI) -> MetricCIDto:
    """Convert a MetricCI dataclass to its HTTP DTO.

    Args:
        ci: MetricCI from the statistics layer.

    Returns:
        MetricCIDto for serialization.
    """
    return MetricCIDto(value=ci.value, ci_lo=ci.ci_lo, ci_hi=ci.ci_hi, n=ci.n)


def metric_bundle_dto(bundle: MetricBundle) -> MetricBundleDto:
    """Convert a MetricBundle to its HTTP DTO.

    Args:
        bundle: Aggregated MetricBundle from the eval layer.

    Returns:
        MetricBundleDto for serialization.
    """
    return MetricBundleDto(
        precision_at_k=metric_ci_dto(bundle.precision_at_k),
        recall_at_k=metric_ci_dto(bundle.recall_at_k),
        ndcg_at_k=metric_ci_dto(bundle.ndcg_at_k),
        turns_to_convergence=metric_ci_dto(bundle.turns_to_convergence),
        avg_cognitive_load=metric_ci_dto(bundle.avg_cognitive_load),
        total_cost_usd=metric_ci_dto(bundle.total_cost_usd),
        drift_events=metric_ci_dto(bundle.drift_events),
        converged_rate=metric_ci_dto(bundle.converged_rate),
        explicit_acceptance_rate=metric_ci_dto(bundle.explicit_acceptance_rate),
        judge_clustering_coherence=metric_ci_dto(bundle.judge_clustering_coherence),
        judge_question_quality=metric_ci_dto(bundle.judge_question_quality),
        judge_profile_fidelity=metric_ci_dto(bundle.judge_profile_fidelity),
    )
