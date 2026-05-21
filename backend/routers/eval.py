import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.repository.eval import (
    JudgeScoreRead,
    SessionMetricsRead,
    count_sessions_per_run,
    list_judge_scores_for_run,
    list_session_metrics_for_run,
)
from backend.repository.runs import get_run, list_runs, Run
from backend.auth import User, require_admin
from backend.eval.aggregator import aggregate_run, aggregate_run_by_persona
from backend.routers.dto.eval.builders import metric_bundle_dto, metric_ci_dto
from backend.routers.dto.eval.dtos import EvalSessionRowDto, MetricBundleDto, MetricCIDto
from backend.routers.dto.runs.dtos import RunDetailDto, RunSummaryDto

log = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["eval"])


def _resolve_run(run_id: uuid.UUID) -> Run:
    """Fetch a run by ID, raising 404 if absent.

    Args:
        run_id: UUID of the run to fetch.

    Returns:
        Run row.

    Raises:
        HTTPException(404): If no run with this id exists.
    """
    try:
        return get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")


@router.get("/runs", response_model=list[RunSummaryDto])
def list_eval_runs(
    _admin: Annotated[User, Depends(require_admin)],
) -> list[RunSummaryDto]:
    """List all eval runs with session counts.

    Returns:
        List of RunSummaryDto ordered by started_at descending.
    """
    log.info("eval list_runs requested by admin user")
    runs = list_runs()
    run_ids = [r.id for r in runs]
    counts = count_sessions_per_run(run_ids)

    return [
        RunSummaryDto(
            id=r.id,
            name=r.name,
            condition=r.condition,
            status=r.status,
            started_at=r.started_at,
            ended_at=r.ended_at,
            n_sessions=counts.get(r.id, 0),
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=RunDetailDto)
def get_eval_run(
    run_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
) -> RunDetailDto:
    """Fetch full run metadata plus overall aggregate metrics.

    Args:
        run_id: UUID of the run.

    Returns:
        RunDetailDto with aggregate MetricBundle.
    """
    log.info("eval get_run run_id=%s", run_id)
    run = _resolve_run(run_id)
    n_sessions = count_sessions_per_run([run_id]).get(run_id, 0)
    bundle = aggregate_run(run_id)

    return RunDetailDto(
        id=run.id,
        name=run.name,
        condition=run.condition,
        config_hash=run.config_hash,
        seed=run.seed,
        model_version=run.model_version,
        status=run.status,
        notes=run.notes,
        started_at=run.started_at,
        ended_at=run.ended_at,
        n_sessions=n_sessions,
        aggregate=metric_bundle_dto(bundle),
    )


@router.get("/runs/{run_id}/aggregate", response_model=MetricBundleDto)
def get_eval_aggregate(
    run_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
) -> MetricBundleDto:
    """Return overall aggregate metrics for a run.

    Args:
        run_id: UUID of the run.

    Returns:
        MetricBundleDto with per-metric 95% CIs across all sessions.
    """
    log.info("eval aggregate run_id=%s", run_id)
    _resolve_run(run_id)
    return metric_bundle_dto(aggregate_run(run_id))


@router.get("/runs/{run_id}/aggregate/by-persona", response_model=dict[str, MetricBundleDto])
def get_eval_aggregate_by_persona(
    run_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
) -> dict[str, MetricBundleDto]:
    """Return per-persona aggregate metrics for a run.

    Sessions with no persona_id are grouped under the key ``"__none__"``.

    Args:
        run_id: UUID of the run.

    Returns:
        Dict mapping persona_id to its MetricBundleDto.
    """
    log.info("eval aggregate_by_persona run_id=%s", run_id)
    _resolve_run(run_id)
    by_persona = aggregate_run_by_persona(run_id)
    return {persona: metric_bundle_dto(bundle) for persona, bundle in by_persona.items()}


@router.get("/runs/{run_id}/sessions", response_model=list[EvalSessionRowDto])
def get_eval_sessions(
    run_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
) -> list[EvalSessionRowDto]:
    """Return raw per-session eval metrics for a run (drill-down table).

    Judge scores are pivoted: one column per dimension, None when missing.

    Args:
        run_id: UUID of the run.

    Returns:
        List of EvalSessionRowDto, one per session that has session_metrics.
    """
    log.info("eval sessions run_id=%s", run_id)
    _resolve_run(run_id)

    metrics = list_session_metrics_for_run(run_id)
    judge_scores = list_judge_scores_for_run(run_id)

    scores_by_session: dict[uuid.UUID, dict[str, int]] = {}
    for j in judge_scores:
        scores_by_session.setdefault(j.session_id, {})[j.dimension] = j.score

    return [
        EvalSessionRowDto(
            session_id=m.session_id,
            persona_id=m.persona_id,
            ground_truth_id=m.ground_truth_id,
            converged=m.converged,
            explicit_acceptance=m.explicit_acceptance,
            turns_to_convergence=m.turns_to_convergence,
            avg_cognitive_load=m.avg_cognitive_load,
            total_cost_usd=m.total_cost_usd,
            drift_events=m.drift_events,
            precision_at_k=m.precision_at_k,
            recall_at_k=m.recall_at_k,
            ndcg_at_k=m.ndcg_at_k,
            judge_clustering_coherence=scores_by_session.get(m.session_id, {}).get(
                "clustering_coherence"
            ),
            judge_question_quality=scores_by_session.get(m.session_id, {}).get(
                "question_quality"
            ),
            judge_profile_fidelity=scores_by_session.get(m.session_id, {}).get(
                "profile_fidelity"
            ),
        )
        for m in metrics
    ]
