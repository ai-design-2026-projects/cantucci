"""Retrieval System agent — converts an oracle query or profile summary into enriched film candidates.

Two entry points cover the two retrieval modes:

- ``retrieve_from_message`` — reformulates the oracle's raw utterance via the LLM,
  extracts any film titles to exclude from the utterance, and runs vector search.
  Used for first-turn and ``proceed`` actions.

- ``retrieve_from_profile`` — reformulates the preference-profile summary via the LLM
  (different prompt, no extraction), then applies a caller-supplied exclusion list
  deterministically before vector search. Used for ``drift_confirmed`` and
  ``re_retrieve`` actions. Exclusions come from the orchestrator's ``seen_films``
  list, guaranteeing they are never dropped by the LLM.

Both functions return the same ``RetrievalResult`` shape so downstream agents
(clustering, render) are unaffected by which path was used.
"""
import logging
from uuid import UUID

from backend.api import movies as api_movies
from backend.api.types import MovieMetadata
from backend.api.types import MovieHit
from backend.retrieval.tools import metadata_fetcher, query_reformulator, vector_search
from backend.retrieval.types import RetrievalResult

log = logging.getLogger(__name__)


def _finalize(
    *,
    hits: list[MovieHit],
    k: int,
    user_query: str,
    reformulated_query: str,
    excluded_films: list[str],
    excluded_movie_ids: list[int],
    session_id: UUID,
    turn_id: UUID,
) -> RetrievalResult:
    """Fetch metadata for *hits*, sort, warn on shortfall, and return a ``RetrievalResult``."""
    metas: list[MovieMetadata] = metadata_fetcher.fetch([h.movie_id for h in hits])
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
            "reformulated_query_len": len(reformulated_query),
            "top_score": hits[0].score if hits else None,
            "n_excluded_resolved": len(excluded_movie_ids),
        },
    )

    return RetrievalResult(
        user_query=user_query,
        reformulated_query=reformulated_query,
        k=k,
        candidates=metas,
        scores=score_map,
        excluded_films=excluded_films,
        excluded_movie_ids=excluded_movie_ids,
    )


def retrieve_from_message(
    *,
    user_query: str,
    k: int,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> RetrievalResult:
    """Reformulate *user_query* via LLM, extract exclusions from the utterance, and return top-k candidates.

    The LLM reads the oracle's raw utterance, writes a HyDE-style search string, and
    extracts any film titles the oracle mentioned. Those titles are fuzzy-matched
    against the catalogue and pushed into the SQL vector search as a negative filter.

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
            "mode": "from_message",
        },
    )

    reformulated = query_reformulator.from_message(
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
            "top_score": hits[0].score if hits else None,
        },
    )

    return _finalize(
        hits=hits,
        k=k,
        user_query=user_query,
        reformulated_query=reformulated.query,
        excluded_films=excluded_titles,
        excluded_movie_ids=exclude_ids,
        session_id=session_id,
        turn_id=turn_id,
    )


def retrieve_from_profile(
    *,
    summary: str,
    excluded_films: list[str],
    k: int,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> RetrievalResult:
    """Reformulate the preference-profile *summary* and return top-k candidates with deterministic exclusions.

    Unlike ``retrieve_from_message``, the LLM only writes a HyDE search string — it
    does NOT extract exclusions. The caller-provided *excluded_films* list (the
    orchestrator's ``seen_films``) is resolved to catalogue IDs and pushed into the
    SQL vector search as a negative filter. This guarantees excluded films are always
    absent from the result, regardless of how the LLM reformulates the summary.

    Args:
        summary:              Preference-profile summary text from the profile agent.
                              Must be non-empty.
        excluded_films:       Film titles / series roots to exclude from results.
                              Resolved to catalogue IDs via fuzzy title match.
        k:                    Maximum number of candidates to return; must be > 0.
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        accumulated_cost_usd: Running USD cost for the current turn (cost guard).
        dry_run:              If ``True``, uses the canned fixture instead of a live LLM call.

    Returns:
        ``RetrievalResult`` with candidates in descending similarity order. ``user_query``
        is set to the profile summary. ``excluded_films`` and ``excluded_movie_ids`` reflect
        the caller-provided exclusion list.

    Raises:
        ValueError:        If *summary* is empty or *k* is not positive.
        LLMParseError:     If reformulation fails JSON validation on every retry.
        CostLimitExceeded: If the session budget is exhausted.
    """
    if not summary.strip():
        raise ValueError("summary must be a non-empty string")
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")

    log.info(
        "retrieval start",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "summary_len": len(summary),
            "n_excluded_films": len(excluded_films),
            "k": k,
            "mode": "from_profile",
        },
    )

    reformulated = query_reformulator.from_profile(
        summary=summary,
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        accumulated_cost_usd=accumulated_cost_usd,
        dry_run=dry_run,
    )
    log.debug(
        "profile query reformulated",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "reformulated_query": reformulated.query,
        },
    )

    exclude_ids: list[int] = (
        api_movies.resolve_titles_to_ids(excluded_films) if excluded_films else []
    )
    if excluded_films:
        log.info(
            "retrieval exclusion resolved",
            extra={
                "n_titles": len(excluded_films),
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
            "top_score": hits[0].score if hits else None,
        },
    )

    return _finalize(
        hits=hits,
        k=k,
        user_query=summary,
        reformulated_query=reformulated.query,
        excluded_films=list(excluded_films),
        excluded_movie_ids=exclude_ids,
        session_id=session_id,
        turn_id=turn_id,
    )
