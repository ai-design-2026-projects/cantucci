import numpy as np

from backend.agents.concept.types import LinearAxisRep


def score_movies(
    concept: LinearAxisRep,
    movie_ids: list[int],
    embeddings: dict[int, list[float]],
) -> dict[int, float]:
    """Score a set of movies against a concept axis.

    Score = dot(movie_embedding, axis_vector). Both vectors are L2-normalized,
    so the result is the cosine similarity (signed position along the axis).

    The caller is responsible for supplying embeddings from the same space as
    the concept axis: ``text_embedding`` for ``space="semantic"`` concepts and
    ``trailer_embedding`` for ``space="visual"`` concepts.

    Args:
        concept:    The concept axis to score against.
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
        scores[mid] = float(np.dot(vec, concept.axis_vector))
    return scores


def normalize_axis_scores(scores: dict[int, float]) -> dict[int, float]:
    """Rescale raw concept scores to the [-1, 1] range via min-max normalization.

    Maps the minimum score to -1 and the maximum to +1 linearly.  When all
    scores are identical (max == min), every movie is mapped to 0.0.

    Args:
        scores: Dict mapping movie_id → raw axis score.

    Returns:
        New dict with the same keys and scores rescaled to [-1, 1].
    """
    if not scores:
        return {}
    values = list(scores.values())
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return {mid: 0.0 for mid in scores}
    span = hi - lo
    return {mid: 2.0 * (v - lo) / span - 1.0 for mid, v in scores.items()}
