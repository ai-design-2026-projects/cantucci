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
