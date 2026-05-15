"""Output types for the Retrieval System agent."""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from backend.api.types import MovieMetadata


class ReformulatedQuery(BaseModel):
    """Structured output of the query reformulator (``query_reformulate_v2.j2``).

    The harness validates the model's JSON response against this schema before
    handing it back to the caller, so any retry-on-invalid-JSON happens inside
    ``llm_harness.call()``.

    Attributes:
        query:          HyDE-style enriched search string fed to vector search.
                        Must be non-empty; the reformulator treats an empty value
                        as a parse failure.
        excluded_films: Film titles or series roots the oracle wants to avoid.
                        Resolved to catalog ``movie_id``s by the retrieval agent
                        via fuzzy title match; mentions that imply a positive
                        preference must NOT appear here (see the prompt rules).
    """

    query: str = Field(min_length=1)
    excluded_films: list[str] = Field(default_factory=list)


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
        excluded_films:     Raw title / series strings emitted by the reformulator
                            for this turn; preserved for replay and observability.
        excluded_movie_ids: Catalog IDs resolved from ``excluded_films`` via fuzzy
                            title match, which were passed to vector search as a
                            negative filter.
    """

    query: str
    k: int
    candidates: list[MovieMetadata]
    scores: dict[int, float]
    reformulated_query: str = ""
    excluded_films: list[str] = field(default_factory=list)
    excluded_movie_ids: list[int] = field(default_factory=list)
