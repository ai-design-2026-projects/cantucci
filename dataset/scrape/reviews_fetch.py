import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx
from tqdm.auto import tqdm

log = logging.getLogger(__name__)

_TMDB_API_BASE = "https://api.themoviedb.org/3"
_REQUEST_TIMEOUT = 30.0
_RETRY_429_SLEEP = 10.0
_MAX_429_RETRIES = 3
_TOP_K_REVIEWS = 10
_MAX_REVIEWS_CHARS = 8000
_REVIEW_SEPARATOR = "\n\n---\n\n"


def fetch_reviews(
    client: httpx.Client,
    api_key: str,
    movie_id: int,
) -> tuple[int, str | None]:
    """Fetch up to ``_TOP_K_REVIEWS`` English reviews for one movie.

    Reviews are sorted descending by author rating before selection so the
    most-opinionated reviews are preferred over chronologically-recent ones.

    Args:
        client:   Shared ``httpx.Client`` instance.
        api_key:  TMDB v3 API key.
        movie_id: TMDB movie identifier.

    Returns:
        ``(movie_id, reviews_text)`` where ``reviews_text`` is ``None`` if the
        movie has no English reviews or returns 404.

    Raises:
        httpx.HTTPStatusError: After ``_MAX_429_RETRIES`` rate-limit responses.
    """
    url = f"{_TMDB_API_BASE}/movie/{movie_id}/reviews"
    params = {"api_key": api_key, "language": "en-US", "page": 1}
    for attempt in range(_MAX_429_RETRIES + 1):
        resp = client.get(url, params=params, timeout=_REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return movie_id, None
        if resp.status_code == 429:
            if attempt >= _MAX_429_RETRIES:
                raise httpx.HTTPStatusError(
                    f"TMDB 429 after {attempt} retries for reviews id {movie_id}",
                    request=resp.request,
                    response=resp,
                )
            log.warning(
                "rate-limited by TMDB (reviews)",
                extra={"id": movie_id, "attempt": attempt, "sleep_for": _RETRY_429_SLEEP},
            )
            time.sleep(_RETRY_429_SLEEP)
            continue
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        results: list[dict[str, Any]] = data.get("results") or []
        if not results:
            return movie_id, None
        results = sorted(
            results,
            key=lambda r: r.get("author_details", {}).get("rating") or 0,
            reverse=True,
        )
        texts = [r.get("content", "") for r in results[:_TOP_K_REVIEWS] if r.get("content")]
        if not texts:
            return movie_id, None
        joined = _REVIEW_SEPARATOR.join(texts)
        return movie_id, joined[:_MAX_REVIEWS_CHARS]
    raise RuntimeError("unreachable")


def fetch_all_reviews(
    api_key: str,
    movie_ids: list[int],
    concurrency: int = 8,
) -> dict[int, str]:
    """Fetch reviews for every id in *movie_ids* concurrently.

    Movies with no English reviews are omitted from the returned dict.

    Args:
        api_key:     TMDB v3 API key.
        movie_ids:   TMDB movie identifiers to query.
        concurrency: Thread-pool worker count.

    Returns:
        Mapping of ``{movie_id: reviews_text}`` for movies that have at least
        one English review.
    """
    results: dict[int, str] = {}
    with (
        httpx.Client(timeout=30.0) as client,
        ThreadPoolExecutor(max_workers=concurrency) as pool,
        tqdm(total=len(movie_ids), desc="TMDB reviews", unit="movie") as bar,
    ):
        futures = {
            pool.submit(fetch_reviews, client, api_key, mid): mid
            for mid in movie_ids
        }
        for fut in as_completed(futures):
            mid, text = fut.result()
            if text is not None:
                results[mid] = text
            bar.update(1)
    log.info(
        "reviews_fetch_complete",
        extra={"total": len(movie_ids), "with_reviews": len(results)},
    )
    return results
