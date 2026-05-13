"""Session and turn HTTP endpoints.

Invariants enforced here:
- No SQL. This layer calls the orchestrator; ``backend/api/`` owns the DB.
- No LLM imports. All model calls happen inside the orchestrator.
- Timestamps are set by the orchestrator (server-side UTC); never read from
  request bodies.
- TODO: add an auth dependency (e.g. X-Oracle-Id header) when auth is designed.
  Per CLAUDE.md, auth lives on the HTTP layer; ``backend/api/`` trusts the IDs
  it receives.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.models.exceptions import MovieNotFound, SessionNotConverged, SessionNotFound
from backend.models.orchestrator import Orchestrator
from backend.models.public import ConvergedClusterPublic, MoviePublic
from backend.models.sessions import SessionState, TurnRequest, TurnResult

log = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ── Dependency ────────────────────────────────────────────────────────────────

def _orchestrator(request: Request) -> Orchestrator:
    """Return the app-scoped orchestrator instance bound in app.state.

    The concrete type is set during the lifespan in ``backend/app.py``.
    If app.state.orchestrator is missing an AttributeError surfaces as 500,
    which is the correct loud-failure behaviour.

    Args:
        request: The current FastAPI request (injected by the DI framework).

    Returns:
        The ``Orchestrator`` instance bound to this application.
    """
    return request.app.state.orchestrator  # type: ignore[return-value]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=SessionState, status_code=201)
def create_session(orchestrator: Orchestrator = Depends(_orchestrator)) -> SessionState:
    """Create a new recommendation session.

    Returns an initial ``SessionState`` with status=active and an empty turn
    list. The session_id in the response is used as the path parameter for
    subsequent turn requests.

    Args:
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        The newly created ``SessionState`` (HTTP 201).
    """
    state = orchestrator.create_session()
    log.info("session created", extra={"session_id": str(state.session_id)})
    return state


@router.post("/{session_id}/turns", response_model=TurnResult)
def add_turn(
    session_id: UUID,
    body: TurnRequest,
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> TurnResult:
    """Submit the user's message for the next turn and get the system's response.

    The response echoes the message back during the placeholder phase. The
    real orchestrator will run a full recommendation pipeline here.

    Args:
        session_id:   UUID of an existing session (path parameter).
        body:         Request body containing ``user_message`` (non-empty).
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        A ``TurnResult`` with the assistant's response and metadata (HTTP 200).

    Raises:
        HTTPException(404): If *session_id* does not identify a live session.
        HTTPException(422): If ``user_message`` is empty or whitespace-only.
    """
    try:
        result = orchestrator.handle_turn(session_id, body.user_message)
    except SessionNotFound as exc:
        log.warning("session not found", extra={"session_id": str(session_id)})
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log.info(
        "turn completed",
        extra={"session_id": str(session_id), "turn_number": result.turn_number},
    )
    return result


@router.get("/{session_id}", response_model=SessionState)
def get_session(
    session_id: UUID,
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> SessionState:
    """Retrieve full session state including all turns in turn_number order.

    Args:
        session_id:   UUID of the session to retrieve (path parameter).
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        The ``SessionState`` with all turns (HTTP 200).

    Raises:
        HTTPException(404): If *session_id* does not identify a live session.
    """
    try:
        state = orchestrator.get_session(session_id)
    except SessionNotFound as exc:
        log.warning("session not found", extra={"session_id": str(session_id)})
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return state


@router.get("/{session_id}/converged-cluster", response_model=ConvergedClusterPublic)
def get_converged_cluster(
    session_id: UUID,
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> ConvergedClusterPublic:
    """Return the fine cluster and enriched movie list for a converged session.

    The cluster and movies are drawn from the last turn's cluster snapshot.
    Call this once after the client detects ``converged=true`` in a TurnResult.

    Args:
        session_id:   UUID of the converged session.
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        A ``ConvergedClusterPublic`` with cluster, movies, and preference profile.

    Raises:
        HTTPException(404): If *session_id* does not exist.
        HTTPException(409): If the session has not yet converged.
    """
    try:
        result = orchestrator.get_converged_cluster(session_id)
    except SessionNotFound as exc:
        log.warning("session not found", extra={"session_id": str(session_id)})
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionNotConverged as exc:
        log.warning(
            "session not converged",
            extra={"session_id": str(session_id), "status": exc.status},
        )
        raise HTTPException(
            status_code=409,
            detail={"code": "not_converged", "message": str(exc)},
        ) from exc
    return result


# ── Movie catalogue ───────────────────────────────────────────────────────────

movies_router = APIRouter(prefix="/movies", tags=["movies"])


@movies_router.get("/{movie_id}", response_model=MoviePublic)
def get_movie(
    movie_id: int,
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> MoviePublic:
    """Return full catalogue metadata for a single movie.

    Args:
        movie_id:     TMDB integer movie id (path parameter).
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        A ``MoviePublic`` with poster URL, synopsis, genres, cast, and ratings.

    Raises:
        HTTPException(404): If *movie_id* is not in the catalogue.
    """
    try:
        movie = orchestrator.get_movie(movie_id)
    except MovieNotFound as exc:
        log.warning("movie not found", extra={"movie_id": movie_id})
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return movie
