from pydantic import BaseModel


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
