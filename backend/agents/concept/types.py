from dataclasses import dataclass
from typing import Literal
import uuid

import numpy as np
from pydantic import BaseModel

from backend.agents.intent.types import Modality


class ConceptLLMResponse(BaseModel):
    """Structured output expected from the concept parsing LLM call.

    The ``space`` discriminator determines which encoder and which movie
    embedding column the resulting axis lives in:

    - ``"semantic"``: requires non-empty ``positive_descriptions`` and
      ``negative_descriptions`` (each a list of 3 distinct full sentences
      describing the respective pole). Encoded with the BGE text encoder;
      scored against ``text_embedding``.
    - ``"visual"``: same list structure but descriptions must be short visual
      phrases (≈3–8 words) to stay within CLIP's 77-token context limit.
      Encoded with the CLIP text tower; scored against ``trailer_embedding``.

    ``positive_label`` and ``negative_label`` are concise 1–3 word pole names
    surfaced in the UI (e.g. ``"hopeful"`` / ``"bleak"``).
    """
    space: Literal["semantic", "visual"]
    positive_descriptions: list[str] = []
    negative_descriptions: list[str] = []
    positive_label: str = ""
    negative_label: str = ""


@dataclass(frozen=True, slots=True)
class LinearAxisRep:
    """A concept represented as a direction vector in embedding space.

    The axis is built by subtracting the centroid of negative exemplars from
    the centroid of positive exemplars, then L2-normalizing.

    Attributes:
        concept_name:   Human-readable concept name.
        space:          ``"semantic"`` → BGE text space; ``"visual"`` → CLIP visual space.
                        Determines which movie embeddings must be loaded for scoring.
        axis_vector:    1024-d unit vector; dot with a matching-space movie embedding
                        gives the concept score.
        cost:           LLM cost in USD for the concept parsing call.
        positive_label: Short label for the HIGH (positive) end of the axis, e.g. ``"hopeful"``.
        negative_label: Short label for the LOW (negative) end of the axis, e.g. ``"bleak"``.
    """
    concept_name: str
    space: Literal["semantic", "visual"]
    axis_vector: np.ndarray
    cost: float
    positive_label: str = ""
    negative_label: str = ""


ConceptRep = LinearAxisRep


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
