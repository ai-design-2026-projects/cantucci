"""Types for the Retrieval System — vector search hits and enriched film metadata."""

from dataclasses import dataclass, field


@dataclass
class MovieHit:
    """A single vector-search result before metadata enrichment."""
    movie_id: int
    title: str
    score: float  # cosine similarity in [0, 1]; higher is more relevant


@dataclass
class MovieMetadata:
    """Enriched film metadata returned by the Librarian (metadata_fetcher) tool.

    Matches the synopsis, genre, and director fields named in architecture.md.
    """
    movie_id: int
    title: str
    overview: str | None
    tagline: str | None
    release_year: int | None
    genres: list[str] = field(default_factory=list)
    director: str | None = None


@dataclass
class RetrievalResult:
    """Output of the Retrieval System for one oracle turn.

    Candidates are ordered by descending cosine similarity (highest score first).
    ``scores`` maps movie_id → similarity so downstream agents can rank without
    re-joining.

    Attributes:
        query:              Original oracle query passed to the retrieval system.
        k:                  Maximum number of candidates requested.
        candidates:         Enriched film metadata in descending similarity order.
        scores:             movie_id → cosine similarity mapping.
        reformulated_query: Vibe-enriched query produced by the reformulator step;
                            empty string if reformulation was skipped (dry_run).
    """

    query: str
    k: int
    candidates: list[MovieMetadata]
    scores: dict[int, float]
    reformulated_query: str = ""
