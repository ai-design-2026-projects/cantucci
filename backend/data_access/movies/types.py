from dataclasses import dataclass, field

TMDB_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"


@dataclass(frozen=True, slots=True)
class MovieSearchHitRow:
    """A single result from a k-NN vector search.

    Attributes:
        movie_id: TMDB integer ID.
        title:    Movie title.
        score:    Cosine similarity in [0, 1].
    """
    movie_id: int
    title: str
    score: float

    @classmethod
    def from_row(cls, r: dict) -> "MovieSearchHitRow":
        """Construct from a psycopg dict_row result of the vector search query."""
        return cls(
            movie_id=r["id"],
            title=r["title"],
            score=float(r["score"]),
        )


@dataclass(frozen=True, slots=True)
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

    @classmethod
    def from_row(cls, r: dict) -> "MovieRow":
        """Construct from a psycopg dict_row result of the fetch_metadata query."""
        return cls(
            movie_id=r["id"],
            title=r["title"],
            overview=r["overview"],
            tagline=r["tagline"],
            release_year=r["release_year"],
            genres=list(r["genres"]) if r["genres"] else [],
            director=r["director"],
        )


@dataclass(frozen=True, slots=True)
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

    @classmethod
    def from_row(cls, r: dict) -> "MovieStubRow":
        """Construct from a psycopg dict_row result of the fetch_stubs query."""
        return cls(
            id=r["id"],
            title=r["title"],
            poster_url=f"{TMDB_POSTER_BASE_URL}{r['poster_path']}" if r["poster_path"] else None,
            release_year=r["release_year"],
            vote_average=r["vote_average"],
        )


@dataclass(frozen=True, slots=True)
class MovieDetailsRow:
    """Full movie projection returned by fetch_movie_details.

    Attributes:
        id:                  TMDB integer ID.
        title:               Movie title.
        release_year:        Release year.
        runtime:             Runtime in minutes.
        vote_average:        TMDB vote average.
        vote_count:          Number of TMDB votes.
        bayesian_rating:     Bayesian-smoothed rating.
        overview:            Plot synopsis.
        poster_url:          Full TMDB poster URL, or None.
        original_language:   ISO 639-1 language code.
        genres:              List of genre names.
        director:            Director name, or None.
        top_cast:            Up to 3 leading cast names.
        trailer_youtube_key: YouTube video key for the official trailer, or None.
        umap_x:              UMAP 2D projection x-coordinate, or None if not yet computed.
        umap_y:              UMAP 2D projection y-coordinate, or None if not yet computed.
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
    trailer_youtube_key: str | None
    umap_x: float | None
    umap_y: float | None

    @classmethod
    def from_row(cls, r: dict) -> "MovieDetailsRow":
        """Construct from a psycopg dict_row result of the fetch_movie_details query."""
        return cls(
            id=r["id"],
            title=r["title"],
            release_year=r["release_year"],
            runtime=r["runtime"],
            vote_average=r["vote_average"],
            vote_count=r["vote_count"],
            bayesian_rating=r["bayesian_rating"],
            overview=r["overview"],
            poster_url=f"{TMDB_POSTER_BASE_URL}{r['poster_path']}" if r["poster_path"] else None,
            original_language=r["original_language"],
            genres=list(r["genres"]) if r["genres"] else [],
            director=r["director"],
            top_cast=list(r["top_cast"]) if r["top_cast"] else [],
            trailer_youtube_key=r["trailer_youtube_key"],
            umap_x=r["umap_x"],
            umap_y=r["umap_y"],
        )
