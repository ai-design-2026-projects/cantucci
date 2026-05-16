import logging

import backend.api.movies as api_movies
from backend.api.types import MovieMetadata

log = logging.getLogger(__name__)


def fetch(movie_ids: list[int]) -> list[MovieMetadata]:
    """
    Return enriched metadata for each film in *movie_ids*.

    Preserves the input order; films not found in the catalogue are silently
    dropped (the caller should treat the catalogue as authoritative).
    
    Args:
        movie_ids: TMDB integer IDs returned by the vector_search tool.

    Returns:
        List of MovieMetadata in the same order as *movie_ids*.
    """
    metadata = api_movies.fetch_metadata(movie_ids)
    log.debug("metadata_fetcher", extra={"requested": len(movie_ids), "returned": len(metadata)})
    return metadata
