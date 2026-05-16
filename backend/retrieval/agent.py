"""Retrieval System agent — converts an oracle query into enriched film candidates.

Pipeline (all owned by this agent, called from the cluster agent with the raw
oracle utterance):

    user_query → query_reformulator (LLM, JSON-validated by harness)
              → resolve excluded titles → movie_ids
              → vector_search (embeds reformulated query) → top-k hits
              → metadata_fetcher → RetrievalResult

The reformulator's LLM call is logged by the harness via ``log_llm_call(...)``;
this module logs deterministic steps (exclusion resolution, vector-search
completion) at INFO and never duplicates the harness record.
"""

import logging
from uuid import UUID

from backend.api import movies as api_movies
from backend.retrieval.tools import metadata_fetcher, query_reformulator, vector_search
from backend.retrieval.types import RetrievalResult

log = logging.getLogger(__name__)


def retrieve(
    *,
    user_query: str,
    k: int,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> RetrievalResult:
    """Reformulate *user_query*, embed it, and return top-k enriched candidates.

    The agent drives the full retrieval pipeline internally so callers (the
    cluster agent) hand over the oracle's raw utterance and receive a
    fully-resolved result. The reformulator is invoked through the LLM harness
    with ``response_schema=ReformulatedQuery``, which guarantees JSON validation
    and emits a ``log_llm_call`` record per attempt. Excluded titles surfaced by
    the reformulator are fuzzy-matched against ``movies.title`` and pushed into
    the SQL vector search as a negative filter at the source.

    Args:
        user_query:           Oracle's raw utterance for this turn.
        k:                    Maximum number of candidates to return; must be > 0.
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        accumulated_cost_usd: Running USD cost for the current turn (cost guard).
        dry_run:              If ``True``, the reformulator uses its canned
                              fixture instead of calling the LLM; the rest of
                              the pipeline runs normally against the catalogue.

    Returns:
        ``RetrievalResult`` with candidates in descending similarity order plus
        the raw oracle utterance, the reformulated search string, and the raw
        and resolved exclusion lists for observability and replay.

    Raises:
        ValueError:        If *user_query* is empty or *k* is not positive.
        LLMParseError:     If reformulation fails JSON validation on every retry.
        CostLimitExceeded: If the session budget is exhausted.
    """
    if not user_query.strip():
        raise ValueError("user_query must be a non-empty string")
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")

    log.info(
        "retrieval start",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "user_query_len": len(user_query),
            "k": k,
        },
    )

    # Reformulate the query and extract exclusions via the LLM harness
    reformulated = query_reformulator.reformulate(
        user_query=user_query,
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        accumulated_cost_usd=accumulated_cost_usd,
        dry_run=dry_run,
    )
    log.debug(
        "query reformulated",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "reformulated_query": reformulated.query,
            "n_excluded_titles": len(reformulated.excluded_films),
        },
    )
    excluded_titles = list(reformulated.excluded_films)
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

    log.debug(
        "vector_search inputs",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "k": k,
            "n_exclude_ids": len(exclude_ids),
            "query_len": len(reformulated.query),
        },
    )

    hits = vector_search.search(reformulated.query, k, exclude_ids=exclude_ids or None)

    log.debug(
        "vector_search result",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "n_hits": len(hits),
            "top_score": hits[0].score if hits else None
        },
    )

    metas = metadata_fetcher.fetch([h.movie_id for h in hits])

    log.debug(
        "metadata fetched",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "n_requested": len(hits),
            "n_returned": len(metas),
            "retrieved_movies": [f"{m.movie_id}: {m.title}" for m in metas],
        },
    )

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
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "k": k,
            "n_returned": n_returned,
            "reformulated_query_len": len(reformulated.query),
            "top_score": hits[0].score if hits else None,
            "n_excluded_resolved": len(exclude_ids),
        },
    )

    return RetrievalResult(
        user_query=user_query,
        reformulated_query=reformulated.query,
        k=k,
        candidates=metas,
        scores=score_map,
        excluded_films=excluded_titles,
        excluded_movie_ids=exclude_ids,
    )
