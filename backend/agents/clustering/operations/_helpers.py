_TOP_EXEMPLARS = 15
_LABEL_PLACEHOLDER = "Cluster"


def exemplars(movie_ids: list[int], probs: list[float], n: int = _TOP_EXEMPLARS) -> list[int]:
    """Return the top-n movie IDs by descending probability.

    Args:
        movie_ids: TMDB integer IDs.
        probs:     Corresponding membership probabilities.
        n:         Maximum number of exemplars to return.

    Returns:
        List of movie IDs sorted by descending probability.
    """
    paired = sorted(zip(probs, movie_ids), reverse=True)
    return [mid for _, mid in paired[:n]]
