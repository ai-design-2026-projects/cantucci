import logging

from fastapi import APIRouter

from backend.data_access.movies.queries import fetch_movie_details
from backend.exceptions import MovieNotFound
from backend.routers.dto.movies.dtos import MovieDto

log = logging.getLogger(__name__)

router = APIRouter(prefix="/movies", tags=["movies"])


@router.get("/{movie_id}", response_model=MovieDto)
def get_movie(movie_id: int) -> MovieDto:
    """Return full metadata for a single movie.

    Args:
        movie_id: TMDB integer ID.

    Returns:
        ``MovieDto`` on success.

    Raises:
        HTTPException(404): If the movie is not in the catalogue.
    """
    rows = fetch_movie_details([movie_id])
    if not rows:
        raise MovieNotFound(movie_id)
    r = rows[0]
    return MovieDto(
        id=r.id,
        title=r.title,
        release_year=r.release_year,
        runtime=r.runtime,
        vote_average=r.vote_average,
        vote_count=r.vote_count,
        bayesian_rating=r.bayesian_rating,
        overview=r.overview,
        poster_url=r.poster_url,
        genres=r.genres,
        director=r.director,
        top_cast=r.top_cast,
        original_language=r.original_language,
        trailer_youtube_key=r.trailer_youtube_key,
    )
