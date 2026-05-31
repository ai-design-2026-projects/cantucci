import logging

from fastapi import APIRouter

from backend.data_access.movies.queries import fetch_movie_details, list_umap_points
from backend.exceptions import MovieNotFound
from backend.routers.dto.movies.dtos import MovieBatchRequest, MovieDto, UmapPointDto, movie_row_to_dto

log = logging.getLogger(__name__)

router = APIRouter(prefix="/movies", tags=["movies"])


@router.get("/umap_points", response_model=list[UmapPointDto])
def get_umap_points() -> list[UmapPointDto]:
    """Return UMAP 2D coordinates for every catalogued movie that has been projected.

    Used by the scatter plot to render a grey silhouette of all films before any
    clustering operation has been performed.  The result is stable after ingest and
    can be cached indefinitely by the client.

    Returns:
        List of ``UmapPointDto`` ordered by movie ID.
    """
    return [UmapPointDto.from_row(r) for r in list_umap_points()]


@router.get("/get/{movie_id}", response_model=MovieDto)
def get_movie(movie_id: int) -> MovieDto:
    """Return full metadata for a single movie by its TMDB integer ID.

    Args:
        movie_id: TMDB integer ID.

    Returns:
        ``MovieDto`` with poster, cast, genres, UMAP coordinates, and ratings.

    Raises:
        HTTPException(404): If the movie is not present in the catalogue.
    """
    rows = fetch_movie_details([movie_id])
    if not rows:
        raise MovieNotFound(movie_id)
    return movie_row_to_dto(rows[0])


@router.post("/get_batch", response_model=list[MovieDto])
def get_movies_batch(body: MovieBatchRequest) -> list[MovieDto]:
    """Return full metadata for up to 200 movies in a single round-trip.

    IDs not present in the catalogue are silently omitted; the returned list
    preserves the input order so callers can zip against their own ID array.

    Args:
        body: ``MovieBatchRequest`` with a list of TMDB integer IDs (max 200).

    Returns:
        List of ``MovieDto`` in the same order as *body.ids*, missing IDs dropped.
    """
    rows = fetch_movie_details(body.ids)
    log.debug("movies_batch", extra={"requested": len(body.ids), "returned": len(rows)})
    return [movie_row_to_dto(r) for r in rows]
