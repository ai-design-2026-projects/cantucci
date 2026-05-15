"""vector_search tool — embeds a text query and fetches top-k similar films."""

import logging
import time

import backend.api.movies as api_movies
from backend.api.types import MovieHit
from backend.settings import get_settings

log = logging.getLogger(__name__)


def search(
    query: str,
    k: int,
    exclude_ids: list[int] | None = None,
) -> list[MovieHit]:
    """Embed *query* and return top-k film hits ordered by cosine similarity.

    Delegates embedding to ``db.ingestion.embed.encode_all`` (same model and
    normalisation as catalogue ingest) and SQL retrieval to
    ``backend.api.movies.vector_search``.

    Args:
        query:       Natural-language search string from the oracle.
        k:           Maximum number of candidates to retrieve.
        exclude_ids: Optional movie_ids to omit from the result (forwarded to
                     ``api.movies.vector_search``); ``None`` or ``[]`` skips
                     exclusion.

    Returns:
        List of MovieHit in descending similarity order.

    Raises:
        ValueError: If *query* is empty or *k* is not positive.
    """
    if not query.strip():
        raise ValueError("query must be a non-empty string")
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")

    from db.ingestion.embed import encode_all

    representation = get_settings().representation
    t0 = time.monotonic()
    embedding = encode_all(
        [query],
        model_name=representation.model,
        expected_dim=representation.embedding_dim,
    )[0]
    latency_ms = (time.monotonic() - t0) * 1000.0

    hits = api_movies.vector_search(embedding, k, exclude_ids=exclude_ids)

    log.debug(
        "vector_search tool",
        extra={
            "query_len": len(query),
            "k": k,
            "top_score": hits[0].score if hits else None,
            "embed_latency_ms": round(latency_ms, 1),
            "n_excluded": len(exclude_ids) if exclude_ids else 0,
        },
    )
    return hits
