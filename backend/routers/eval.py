"""Admin-only evaluation read endpoints.

All routes require an authenticated admin user. Returns paginated or single-item
views of runs, sessions, ground truths, and personas.
"""
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.auth.types import User
from backend.data_access.eval.queries import (
    get_conversation_metrics,
    get_eval_session,
    get_judge_scores,
    get_persona_by_id,
    get_run,
    get_run_aggregate,
    list_eval_sessions_for_run,
    list_ground_truths,
    list_personas,
    list_runs,
    list_turn_intents,
)
from backend.exceptions import NotFoundError
from backend.routers.auth_deps import require_admin
from backend.routers.dto.eval.builders import (
    build_run_aggregate_dto,
    eval_session_to_detail_dto,
    eval_session_to_dto,
    ground_truth_to_dto,
    persona_to_dto,
    run_to_dto,
)
from backend.routers.dto.eval.dtos import (
    EvalSessionDetailDto,
    EvalSessionDto,
    GroundTruthDto,
    PersonaDto,
    RunAggregateDto,
    RunDto,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("/list_runs", response_model=list[RunDto])
def list_runs_endpoint(
    limit: int = 50,
    offset: int = 0,
    _admin: Annotated[User, Depends(require_admin)] = ...,
) -> list[RunDto]:
    """Return a paginated list of eval runs, ordered newest first.

    Args:
        limit:  Maximum number of runs to return (default 50).
        offset: Pagination offset for cursor-style paging (default 0).

    Returns:
        List of ``RunDto`` ordered by ``started_at`` descending.
    """
    rows = list_runs(limit=limit, offset=offset)
    return [run_to_dto(r) for r in rows]


@router.get("/get_run/{run_id}", response_model=RunDto)
def get_run_endpoint(
    run_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)] = ...,
) -> RunDto:
    """Return a single eval run by ID.

    Args:
        run_id: UUID of the eval run.

    Returns:
        ``RunDto`` for the requested run.

    Raises:
        NotFoundError: If the run does not exist.
    """
    row = get_run(run_id)
    if row is None:
        raise NotFoundError(f"run {run_id} not found")
    return run_to_dto(row)


@router.get("/get_run_aggregate/{run_id}", response_model=RunAggregateDto)
def get_run_aggregate_endpoint(
    run_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)] = ...,
) -> RunAggregateDto:
    """Return a run with per-session metrics, latest judge scores, and summary KPIs.

    All sessions for the run are fetched in a single SQL round-trip. Per-session
    metrics and the latest judge score per dimension are inlined. Per-turn intent
    data is not included here — use ``/eval/get_session/{id}`` for that detail.

    Args:
        run_id: UUID of the eval run.

    Returns:
        ``RunAggregateDto`` with run metadata, per-session rows, and summary KPIs.

    Raises:
        NotFoundError: If the run does not exist.
    """
    run, sessions = get_run_aggregate(run_id)
    if run is None:
        raise NotFoundError(f"run {run_id} not found")
    log.info("run_aggregate_fetched", extra={"run_id": str(run_id), "n_sessions": len(sessions)})
    return build_run_aggregate_dto(run, sessions)


@router.get("/list_sessions/{run_id}", response_model=list[EvalSessionDto])
def list_sessions_endpoint(
    run_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)] = ...,
) -> list[EvalSessionDto]:
    """Return all eval sessions for a given run.

    Args:
        run_id: UUID of the parent eval run.

    Returns:
        List of ``EvalSessionDto`` for the run.
    """
    rows = list_eval_sessions_for_run(run_id)
    return [eval_session_to_dto(r) for r in rows]


@router.get("/get_session/{eval_session_id}", response_model=EvalSessionDetailDto)
def get_session_endpoint(
    eval_session_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)] = ...,
) -> EvalSessionDetailDto:
    """Return full detail for a single eval session.

    Includes conversation metrics, judge scores across all four dimensions, and
    per-turn intent records — the full picture of what the simulated oracle did
    during the session.

    Args:
        eval_session_id: UUID of the eval session.

    Returns:
        ``EvalSessionDetailDto`` with nested metrics, scores, and intent records.

    Raises:
        NotFoundError: If the eval session does not exist.
    """
    session = get_eval_session(eval_session_id)
    if session is None:
        raise NotFoundError(f"eval session {eval_session_id} not found")

    metrics = get_conversation_metrics(session.conversation_id)
    judge_scores = get_judge_scores(session.conversation_id)
    turn_intents = list_turn_intents(session.conversation_id)
    persona = get_persona_by_id(session.persona_id) if session.persona_id else None

    return eval_session_to_detail_dto(session, metrics, judge_scores, turn_intents, persona)


@router.get("/list_ground_truths", response_model=list[GroundTruthDto])
def list_ground_truths_endpoint(
    _admin: Annotated[User, Depends(require_admin)] = ...,
) -> list[GroundTruthDto]:
    """Return all ground truth trajectories used as oracle reference conversations.

    Returns:
        List of ``GroundTruthDto`` ordered by ``created_at`` descending.
    """
    rows = list_ground_truths()
    return [ground_truth_to_dto(r) for r in rows]


@router.get("/list_personas", response_model=list[PersonaDto])
def list_personas_endpoint(
    _admin: Annotated[User, Depends(require_admin)] = ...,
) -> list[PersonaDto]:
    """Return all evaluation personas used to drive simulated oracle sessions.

    Returns:
        List of ``PersonaDto``.
    """
    rows = list_personas()
    return [persona_to_dto(r) for r in rows]
