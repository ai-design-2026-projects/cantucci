"""Retrieval System agent — converts an oracle query into enriched film candidates.

No LLM is used in this version. Query reformulation is performed upstream by
``backend.retrieval.tools.query_reformulator``; the agent itself only embeds,
optionally filters out caller-supplied excluded titles, and enriches with
metadata.

Pipeline:
    query (text) → embedded → vector_search (with exclusion filter)
                  → metadata_fetcher → RetrievalResult
"""

import logging

from backend.api import movies as api_movies
from backend.retrieval.types import RetrievalResult
from backend.retrieval.tools import metadata_fetcher, vector_search

log = logging.getLogger(__name__)


def retrieve(
    *,
    query: str,
    k: int,
    exclude_titles: list[str] | None = None,
) -> RetrievalResult:
    """Return top-k candidate films matching *query*, enriched with metadata.

    When *exclude_titles* is non-empty, each title is fuzzy-matched against
    ``movies.title`` (via :func:`backend.api.movies.resolve_titles_to_ids`) and
    the resulting catalog IDs are excluded from the SQL vector search at the
    source — so a request for ``"Lord of the Rings"`` removes all three films
    from candidate consideration, ``"Spider-Man"`` removes every Spider-Man
    release, and so on. Titles that fail to fuzzy-match anything are silently
    skipped (the reformulator may invent or mis-spell titles).

    Args:
        query:          Natural-language preference string from the oracle.
        k:              Maximum number of candidates to return.
        exclude_titles: Optional film titles or series roots to exclude from
                        the result set. Resolved to ``movie_id``s before
                        retrieval.

    Returns:
        RetrievalResult with candidates in descending similarity order plus the
        raw and resolved exclusion lists for observability/replay.

    Raises:
        ValueError: If *query* is empty or *k* is not positive.
    """
    if not query.strip():
        raise ValueError("query must be a non-empty string")
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")

    excluded_titles = list(exclude_titles) if exclude_titles else []
    exclude_ids: list[int] = (
        api_movies.resolve_titles_to_ids(excluded_titles) if excluded_titles else []
    )

    if excluded_titles:
        log.info(
            "retrieval exclusion resolved",
            extra={
                "n_titles": len(excluded_titles),
                "n_excluded_ids": len(exclude_ids),
            },
        )

    hits = vector_search.search(query, k, exclude_ids=exclude_ids or None)
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
            "n_excluded": len(exclude_ids),
        },
    )

    return RetrievalResult(
        query=query,
        k=k,
        candidates=metas,
        scores=score_map,
        excluded_films=excluded_titles,
        excluded_movie_ids=exclude_ids,
    )
