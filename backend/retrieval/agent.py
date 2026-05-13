"""Retrieval System agent — converts an oracle query into enriched film candidates.

No LLM is used in this version. Query reformulation is deferred; the raw oracle
query is embedded directly.

Pipeline:
    query (text) → embedded → vector_search → metadata_fetcher → RetrievalResult
"""

import logging

from backend.retrieval.types import RetrievalResult
from backend.retrieval.tools import metadata_fetcher, vector_search

log = logging.getLogger(__name__)


def retrieve(
    *,
    query: str,
    k: int
) -> RetrievalResult:
    """Return top-k candidate films matching *query*, enriched with metadata.

    Args:
        query:              Natural-language preference string from the oracle.
        k:                  Maximum number of candidates to return.

    Returns:
        RetrievalResult with candidates in descending similarity order.

    Raises:
        ValueError: If *query* is empty or *k* is not positive.

    Note:
        ``active_constraints`` is a forward-compatible parameter. Applying
        constraints requires LLM-driven parsing (out of scope for v1). Until
        implemented, non-empty constraints are logged as a warning rather than
        silently ignored or raised as an error, since this is an expected
        in-progress state rather than a usage mistake.
    """
    if not query.strip():
        raise ValueError("query must be a non-empty string")
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")

    hits = vector_search.search(query, k)
    metas = metadata_fetcher.fetch([h.movie_id for h in hits])

    score_map = {h.movie_id: h.score for h in hits}
    hit_order = {h.movie_id: i for i, h in enumerate(hits)}
    metas.sort(key=lambda m: hit_order.get(m.movie_id, len(hits)))

    n_returned = len(metas)
    if n_returned < k:
        log.warning(
            "retrieval returned fewer candidates than requested",
            extra={"requested": k, "returned": n_returned},
        )

    log.info(
        "retrieval complete",
        extra={
            "query_len": len(query),
            "k": k,
            "n_returned": n_returned,
            "top_score": hits[0].score if hits else None,
        },
    )

    return RetrievalResult(
        query=query,
        k=k,
        candidates=metas,
        scores=score_map,
    )
