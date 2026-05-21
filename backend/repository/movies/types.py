from dataclasses import dataclass, field


@dataclass
class MovieRow:
    """Enriched film metadata returned by the Retriever and stored in the movies table."""
    movie_id: int
    title: str
    overview: str | None
    tagline: str | None
    release_year: int | None
    genres: list[str] = field(default_factory=list)
    director: str | None = None


@dataclass
class MovieStubRow:
    """Lightweight movie projection for cluster snapshot payloads."""
    id: int
    title: str
    poster_url: str | None
    release_year: int | None
    vote_average: float | None


@dataclass
class MovieDetailsRow:
    """Full movie projection returned by fetch_movie_details; mirrors MovieDto fields."""
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
