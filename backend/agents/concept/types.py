from dataclasses import dataclass, field
from typing import Literal
import uuid

import numpy as np
from pydantic import BaseModel

from backend.agents.intent.types import Modality


class ConceptLLMResponse(BaseModel):
    """Structured output expected from the concept parsing LLM call.

    The ``type`` discriminator determines which representation to build:

    - ``"linear_axis"``: requires non-empty ``positive_descriptions`` and
      ``negative_descriptions`` (each a list of 3 distinct sentences describing
      the respective pole). Multiple sentences per pole produce a more stable
      axis direction via centroid averaging. ``positive_label`` and
      ``negative_label`` are concise 1–3 word pole names surfaced in the UI.
    - ``"prototype"``: requires at least one entry in ``exemplar_titles``;
      the description and label fields are ignored.
    """
    type: Literal["linear_axis", "prototype"]
    positive_descriptions: list[str] = []
    negative_descriptions: list[str] = []
    exemplar_titles: list[str] = []
    positive_label: str = ""
    negative_label: str = ""


@dataclass(frozen=True, slots=True)
class LinearAxisRep:
    """A concept represented as a direction vector in embedding space.

    The axis is built by subtracting the centroid of negative exemplars from
    the centroid of positive exemplars, then L2-normalizing.

    Attributes:
        concept_name:    Human-readable concept name.
        axis_vector:     Unit vector; dot with a movie embedding gives the score.
        embedding_space: Modality the axis lives in (``"text"`` by default).
                         Determines which movie embeddings must be loaded for scoring.
        cost:            LLM cost in USD for the concept parsing call.
        positive_label:  Short label for the HIGH (positive) end of the axis, e.g. "hopeful".
        negative_label:  Short label for the LOW (negative) end of the axis, e.g. "bleak".
    """
    concept_name: str
    axis_vector: np.ndarray
    embedding_space: str
    cost: float
    positive_label: str = ""
    negative_label: str = ""


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


@dataclass(frozen=True, slots=True)
class PendingConcept:
    """Stores the context of a concept-axis proposal that is awaiting user confirmation.

    Created when the concept-cluster branch proposes the beeswarm distribution and
    sets the awaiting flag.  Consumed on the next turn by the coordinator, which
    patches the CLUSTER action to reuse the already-scored and persisted concept
    instead of invoking the concept agent again.

    Attributes:
        concept_id:        UUID of the persisted concept whose normalized scores back
                           the beeswarm.
        concept_name:      Human-readable name (e.g. ``"open-ended ending"``).
        target_cluster_id: The cluster the user originally asked to split, or None for
                           the full catalogue / current snapshot.
        embedding_spaces:  Modalities that were used for scoring; carried forward so
                           the reuse branch loads the same embeddings.
    """
    concept_id: uuid.UUID
    concept_name: str
    target_cluster_id: uuid.UUID | None
    embedding_spaces: list[Modality]
