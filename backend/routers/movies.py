"""Movie catalogue HTTP endpoints."""

import logging

from fastapi import APIRouter, HTTPException

from backend.api.movies import fetch_movies_dto
from backend.exceptions import MovieNotFound
from backend.routers.dtos import MovieDto

log = logging.getLogger(__name__)

router = APIRouter(prefix="/movies", tags=["movies"])


@router.get("/{movie_id}", response_model=MovieDto)
def get_movie(movie_id: int) -> MovieDto:
    """Return full metadata for a single movie from the catalogue.

    Args:
        movie_id: TMDB integer ID (path parameter).

    Returns:
        Full ``MovieDto`` payload (HTTP 200).

    Raises:
        HTTPException(404): If the movie is not in the catalogue.
    """
    rows = fetch_movies_dto([movie_id])
    if not rows:
        log.debug("movie not found", extra={"movie_id": movie_id})
        raise HTTPException(status_code=404, detail=str(MovieNotFound(movie_id)))
    log.debug("GET /movies/{id}", extra={"movie_id": movie_id})
    return MovieDto(**rows[0])
