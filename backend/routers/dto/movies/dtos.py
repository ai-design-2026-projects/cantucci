from pydantic import BaseModel, Field

from backend.data_access.movies.types import MovieDetailsRow, UmapPointRow


class UmapPointDto(BaseModel):
    """Minimal UMAP projection for scatter-plot silhouette rendering.

    Attributes:
        movie_id: TMDB integer ID.
        title:    Movie title.
        umap_x:   UMAP 2D x-coordinate.
        umap_y:   UMAP 2D y-coordinate.
    """

    movie_id: int
    title: str
    umap_x: float
    umap_y: float

    @classmethod
    def from_row(cls, r: UmapPointRow) -> "UmapPointDto":
        """Convert a ``UmapPointRow`` to its wire DTO."""
        return cls(movie_id=r.movie_id, title=r.title, umap_x=r.umap_x, umap_y=r.umap_y)


class MovieDto(BaseModel):
    """Full movie metadata as exposed to the frontend.

    Attributes:
        id:                  TMDB movie id.
        title:               English release title.
        release_year:        4-digit year, or None.
        runtime:             Duration in minutes, or None.
        vote_average:        TMDB mean rating 0–10.
        vote_count:          Number of TMDB votes.
        bayesian_rating:     Bayesian-smoothed rating (preferred ranking signal).
        overview:            Plot synopsis.
        poster_url:          Full TMDB poster URL (``https://image.tmdb.org/t/p/w500{path}``),
                             or None when ``poster_path`` is absent.
        genres:              List of genre names.
        director:            Director name, or None.
        top_cast:            Up to 3 top-billed cast names.
        original_language:   ISO 639-1 language code.
        trailer_youtube_key: YouTube video key for the official trailer, or None.
        umap_x:              UMAP 2D projection x-coordinate for scatter visualization, or None.
        umap_y:              UMAP 2D projection y-coordinate for scatter visualization, or None.
    """

    id: int
    title: str
    release_year: int | None
    runtime: float | None
    vote_average: float | None
    vote_count: int | None
    bayesian_rating: float | None
    overview: str | None
    poster_url: str | None
    genres: list[str]
    director: str | None
    top_cast: list[str]
    original_language: str | None
    trailer_youtube_key: str | None
    umap_x: float | None
    umap_y: float | None


class MovieBatchRequest(BaseModel):
    """Body for ``POST /movies/batch``.

    Attributes:
        ids: Up to 200 TMDB movie IDs to retrieve in one request.
    """
    ids: list[int] = Field(..., max_length=200)


def movie_row_to_dto(r: MovieDetailsRow) -> MovieDto:
    """Convert a ``MovieDetailsRow`` to its wire ``MovieDto``.

    Args:
        r: A ``MovieDetailsRow`` from the data-access layer.

    Returns:
        ``MovieDto`` ready for serialization.
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
