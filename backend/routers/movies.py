import logging

from fastapi import APIRouter

from backend.data_access.movies.queries import fetch_movie_details, get_movies_by_ids
from backend.exceptions import MovieNotFound
from backend.routers.dto.movies.dtos import MovieBatchRequest, MovieDto

log = logging.getLogger(__name__)

router = APIRouter(prefix="/movies", tags=["movies"])


def _row_to_dto(r) -> MovieDto:
    """Map a ``MovieDetailsRow`` to a ``MovieDto``.

    @param r: ``MovieDetailsRow`` instance.
    @returns: ``MovieDto`` wire model.
    """
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
        umap_x=r.umap_x,
        umap_y=r.umap_y,
    )


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
    return _row_to_dto(rows[0])


@router.post("/batch", response_model=list[MovieDto])
def get_movies_batch(body: MovieBatchRequest) -> list[MovieDto]:
    """Return full metadata for up to 200 movies in a single request.

    IDs not present in the catalogue are silently omitted; the returned list
    preserves the input order and drops unknown IDs.

    Args:
        body: ``MovieBatchRequest`` with a list of TMDB integer IDs (max 200).

    Returns:
        List of ``MovieDto`` in the same order as *body.ids*, missing IDs dropped.
    """
    rows = get_movies_by_ids(body.ids)
    log.debug("movies_batch", extra={"requested": len(body.ids), "returned": len(rows)})
    return [_row_to_dto(r) for r in rows]
