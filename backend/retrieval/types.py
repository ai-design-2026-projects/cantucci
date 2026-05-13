"""Output types for the Retrieval System agent."""

from dataclasses import dataclass, field

from backend.api.types import MovieMetadata


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
