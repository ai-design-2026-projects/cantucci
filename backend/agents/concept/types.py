from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from pydantic import BaseModel


class ConceptLLMResponse(BaseModel):
    """Structured output expected from the concept parsing LLM call.

    The ``type`` discriminator determines which representation to build:

    - ``"linear_axis"``: requires non-null ``positive_description`` and
      ``negative_description``; ``exemplar_titles`` is ignored.
    - ``"prototype"``: requires at least one entry in ``exemplar_titles``;
      the description fields are ignored.
    """
    type: Literal["linear_axis", "prototype"]
    positive_description: str | None = None
    negative_description: str | None = None
    exemplar_titles: list[str] = []


@dataclass(frozen=True, slots=True)
class LinearAxisRep:
    """A concept represented as a direction vector in embedding space.

    The axis is built by subtracting the centroid of negative exemplars from
    the centroid of positive exemplars, then L2-normalizing.

    Attributes:
        concept_name: Human-readable concept name.
        axis_vector:  1024-d unit vector; dot with a movie embedding gives the score.
        cost:         LLM cost in USD for the concept parsing call.
    """
    concept_name: str
    axis_vector: np.ndarray
    cost: float


@dataclass(frozen=True, slots=True)
class PrototypeRep:
    """A concept represented as the centroid of exemplar movie embeddings.

    Attributes:
        concept_name:       Human-readable concept name.
        centroid:           1024-d mean of exemplar embeddings (L2-normalized).
        exemplar_movie_ids: TMDB IDs of the exemplar movies used to build the centroid.
        cost:               LLM cost in USD for the concept parsing call.
    """
    concept_name: str
    centroid: np.ndarray
    exemplar_movie_ids: list[int] = field(default_factory=list)
    cost: float = 0.0


ConceptRep = LinearAxisRep | PrototypeRep
