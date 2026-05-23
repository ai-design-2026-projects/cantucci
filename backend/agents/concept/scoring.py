import numpy as np

from backend.agents.concept.types import ConceptRep, LinearAxisRep


def score_movies(
    concept: ConceptRep,
    movie_ids: list[int],
    embeddings: dict[int, list[float]],
) -> dict[int, float]:
    """Score a set of movies against a concept representation.

    For ``LinearAxisRep``: score = dot(movie_embedding, axis_vector).
    For ``PrototypeRep``: score = cosine_similarity(movie_embedding, centroid).

    Args:
        concept:    The concept representation to score against.
        movie_ids:  List of TMDB IDs to score.
        embeddings: Pre-fetched embedding dict {movie_id: [float, ...]}.

    Returns:
        Dict mapping movie_id → score. Movies missing from embeddings are omitted.
    """
    scores: dict[int, float] = {}
    for mid in movie_ids:
        if mid not in embeddings:
            continue
        vec = np.array(embeddings[mid], dtype=np.float32)
        if isinstance(concept, LinearAxisRep):
            scores[mid] = float(np.dot(vec, concept.axis_vector))
        else:
            scores[mid] = float(np.dot(vec, concept.centroid))
    return scores
