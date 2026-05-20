import logging
import numpy as np

import backend.repository.movies as api_movies
from backend.settings import get_settings

log = logging.getLogger(__name__)

def fetch(movie_ids: list[int]) -> tuple[list[int], np.ndarray]:
    """Return aligned (kept_ids, embedding_matrix) for *movie_ids*.

    IDs that are missing from the catalogue are silently dropped, matching the
    semantics of ``fetch_metadata``.

    Args:
        movie_ids: TMDB integer IDs to look up.

    Returns:
        A tuple ``(kept_ids, matrix)`` where:
        - ``kept_ids`` is the subset of *movie_ids* found in the catalogue,
          in the same relative order.
                - ``matrix`` is a float32 NumPy array with the configured embedding dimension.

    Raises:
        ValueError: If no embeddings are found for any of *movie_ids*, or if
                    any stored embedding has a dimension other than the configured one.
    """
    expected_dim = get_settings().representation.embedding_dim
    raw = api_movies.fetch_embeddings(movie_ids)

    kept_ids = [mid for mid in movie_ids if mid in raw]
    if not kept_ids:
        raise ValueError(
            f"fetch_embeddings returned no rows for {len(movie_ids)} requested IDs"
        )

    rows = [raw[mid] for mid in kept_ids]
    for i, row in enumerate(rows):
        if len(row) != expected_dim:
            raise ValueError(
                f"movie_id {kept_ids[i]}: expected embedding dim {expected_dim}, "
                f"got {len(row)}"
            )

    matrix = np.array(rows, dtype=np.float32)

    log.debug(
        "embedding_fetcher",
        extra={"requested": len(movie_ids), "returned": len(kept_ids)},
    )
    return kept_ids, matrix
