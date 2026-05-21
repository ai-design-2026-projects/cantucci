from dataclasses import dataclass, field


@dataclass
class MovieSearchHit:
    """A single result from a k-NN vector search.

    Attributes:
        movie_id: TMDB integer ID.
        title:    Movie title.
        score:    Cosine similarity in [0, 1].
    """
    movie_id: int
    title: str
    score: float


@dataclass
class MovieRow:
    """Enriched movie metadata for agent consumption.

    Attributes:
        movie_id:     TMDB integer ID.
        title:        Movie title.
        overview:     Plot synopsis.
        tagline:      Marketing tagline.
        release_year: Release year.
        genres:       List of genre names.
        director:     Director name, if available.
    """
    movie_id: int
    title: str
    overview: str | None
    tagline: str | None
    release_year: int | None
    genres: list[str] = field(default_factory=list)
    director: str | None = None


@dataclass
class MovieStubRow:
    """Lightweight movie projection for cluster snapshots and exemplar lists.

    Attributes:
        id:           TMDB integer ID.
        title:        Movie title.
        poster_url:   Full TMDB poster URL, or None.
        release_year: Release year.
        vote_average: TMDB vote average.
    """
    id: int
    title: str
    poster_url: str | None
    release_year: int | None
    vote_average: float | None


@dataclass
class MovieDetailsRow:
    """Full movie projection returned by fetch_movie_details.

    Attributes:
        id:                TMDB integer ID.
        title:             Movie title.
        release_year:      Release year.
        runtime:           Runtime in minutes.
        vote_average:      TMDB vote average.
        vote_count:        Number of TMDB votes.
        bayesian_rating:   Bayesian-smoothed rating.
        overview:          Plot synopsis.
        poster_url:        Full TMDB poster URL, or None.
        original_language: ISO 639-1 language code.
        genres:            List of genre names.
        director:          Director name, or None.
        top_cast:          Up to 3 leading cast names.
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
    original_language: str | None
    genres: list[str]
    director: str | None
    top_cast: list[str]
