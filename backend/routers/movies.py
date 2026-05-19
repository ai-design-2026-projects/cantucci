"""Movie catalogue HTTP endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.exceptions import MovieNotFound
from backend.orchestrator.orchestrator import Orchestrator
from backend.routers.dtos import MovieDto

log = logging.getLogger(__name__)

router = APIRouter(prefix="/movies", tags=["movies"])


def _orchestrator(request: Request) -> Orchestrator:
    """Return the app-scoped orchestrator instance bound in app.state."""
    return request.app.state.orchestrator  # type: ignore[return-value]


@router.get("/get_movie/{movie_id}", response_model=MovieDto)
def get_movie(
    movie_id: int,
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> MovieDto:
    """Return full metadata for a single movie from the catalogue.

    Args:
        movie_id:     TMDB integer ID (path parameter).
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        Full ``MovieDto`` payload (HTTP 200).

    Raises:
        HTTPException(404): If the movie is not in the catalogue.
    """
    dto = orchestrator.get_movie(movie_id)
    if dto is None:
        log.debug("movie not found", extra={"movie_id": movie_id})
        raise HTTPException(status_code=404, detail=str(MovieNotFound(movie_id)))
    log.debug("GET /movies/{id}", extra={"movie_id": movie_id})
    return dto
