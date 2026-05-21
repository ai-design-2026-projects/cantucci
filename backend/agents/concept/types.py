from dataclasses import dataclass, field

import numpy as np


@dataclass
class LinearAxisRep:
    """A concept represented as a direction vector in embedding space.

    The axis is built by subtracting the centroid of negative exemplars from
    the centroid of positive exemplars, then L2-normalizing.

    Attributes:
        concept_name: Human-readable concept name.
        axis_vector:  1024-d unit vector; dot with a movie embedding gives the score.
    """
    concept_name: str
    axis_vector: np.ndarray


@dataclass
class PrototypeRep:
    """A concept represented as the centroid of exemplar movie embeddings.

    Attributes:
        concept_name:      Human-readable concept name.
        centroid:          1024-d mean of exemplar embeddings (L2-normalized).
        exemplar_movie_ids: TMDB IDs of the exemplar movies used to build the centroid.
    """
    concept_name: str
    centroid: np.ndarray
    exemplar_movie_ids: list[int] = field(default_factory=list)


ConceptRep = LinearAxisRep | PrototypeRep
