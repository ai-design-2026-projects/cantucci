import uuid

from pydantic import BaseModel


class AxisPointDto(BaseModel):
    """A single movie's position on the concept linear axis.

    Attributes:
        movie_id: TMDB integer ID.
        title:    Movie display title.
        score:    Normalized axis score in [-1, 1].
    """
    movie_id: int
    title: str
    score: float


class AxisDistributionDto(BaseModel):
    """Distribution of movies along a concept's linear axis.

    Attributes:
        concept_id:   UUID of the concept.
        concept_name: Human-readable concept name (e.g. ``"open-ended ending"``).
        points:       Per-movie axis points ordered by ascending score.
    """
    concept_id: uuid.UUID
    concept_name: str
    points: list[AxisPointDto]
