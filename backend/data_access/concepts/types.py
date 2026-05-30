import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ConceptRow:
    """A row from the concepts table.

    Attributes:
        id:         Concept UUID.
        name:       Human-readable concept name (e.g. ``"surrealism"``).
        type:       ``"linear_axis"`` or ``"prototype"``.
        definition: JSONB dict encoding the concept representation.
        created_at: UTC creation timestamp.
    """
    id: uuid.UUID
    name: str
    type: str
    definition: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "ConceptRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            name=r["name"],
            type=r["type"],
            definition=r["definition"],
            created_at=r["created_at"],
        )


@dataclass(frozen=True, slots=True)
class ConceptScoreRow:
    """A row from the concept_scores table.

    Attributes:
        concept_id: Concept UUID.
        movie_id:   TMDB integer ID.
        score:      Concept relevance score, typically in [-1, 1] or [0, 1].
    """
    concept_id: uuid.UUID
    movie_id: int
    score: float

    @classmethod
    def from_row(cls, r: dict) -> "ConceptScoreRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            concept_id=r["concept_id"],
            movie_id=r["movie_id"],
            score=float(r["score"]),
        )


@dataclass(frozen=True, slots=True)
class ConceptAxisPointRow:
    """A per-movie point on the concept linear axis, enriched with title for display.

    Attributes:
        movie_id:   TMDB integer ID.
        title:      Movie title from the movies table.
        score:      Normalized axis score in [-1, 1].
        vote_count: Number of TMDB votes; used client-side to highlight pole-representative movies.
    """
    movie_id: int
    title: str
    score: float
    vote_count: int

    @classmethod
    def from_row(cls, r: dict) -> "ConceptAxisPointRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            movie_id=r["movie_id"],
            title=r["title"],
            score=float(r["score"]),
            vote_count=int(r["vote_count"] or 0),
        )
