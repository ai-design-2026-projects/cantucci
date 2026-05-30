import uuid

from pydantic import BaseModel


class AxisPointDto(BaseModel):
    """A single movie's position on the concept linear axis.

    Attributes:
        movie_id:   TMDB integer ID.
        title:      Movie display title.
        score:      Normalized axis score in [-1, 1].
        vote_count: Number of TMDB votes; used client-side to highlight pole-representative movies.
    """
    movie_id: int
    title: str
    score: float
    vote_count: int


class AxisDistributionDto(BaseModel):
    """Distribution of movies along a concept's linear axis.

    Attributes:
        concept_id:     UUID of the concept.
        concept_name:   Human-readable concept name (e.g. ``"open-ended ending"``).
        positive_label: Short label for the HIGH (positive) end of the axis, e.g. ``"hopeful"``.
        negative_label: Short label for the LOW (negative) end of the axis, e.g. ``"bleak"``.
        points:         Per-movie axis points ordered by ascending score.
    """
    concept_id: uuid.UUID
    concept_name: str
    positive_label: str
    negative_label: str
    points: list[AxisPointDto]
