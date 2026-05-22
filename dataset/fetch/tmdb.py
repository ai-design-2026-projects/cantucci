import gzip
import io
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from tqdm.auto import tqdm

log = logging.getLogger(__name__)

_TMDB_API_BASE = "https://api.themoviedb.org/3"
_TMDB_EXPORTS_BASE = "http://files.tmdb.org/p/exports"
_REQUEST_TIMEOUT = 30.0
_RETRY_429_SLEEP = 10.0
_RETRY_TIMEOUT_SLEEP = 2.0
_MAX_429_RETRIES = 3

_TOP_K_REVIEWS = 10
_MAX_REVIEWS_CHARS = 8000
_REVIEW_SEPARATOR = "\n\n---\n\n"


def _export_url(when: datetime) -> str:
    """Return the daily id-export URL for *when* (UTC).

    The export file is published around 08:00 UTC, so callers before that
    hour are silently rolled back one day to a guaranteed-available file.
    """
    if when.hour < 8:
        when = when - timedelta(days=1)
    return f"{_TMDB_EXPORTS_BASE}/movie_ids_{when:%m_%d_%Y}.json.gz"


def _tmdb_get(
    client: httpx.Client,
    path: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """GET ``${_TMDB_API_BASE}/{path}`` with 429-retry semantics.

    Returns the parsed JSON body, or ``None`` on 404. Raises
    ``HTTPStatusError`` after ``_MAX_429_RETRIES`` sustained rate-limit
    responses or on any other non-2xx. Used by both ``fetch_movie`` and
    ``fetch_reviews``.
    """
    url = f"{_TMDB_API_BASE}/{path}"
    for attempt in range(_MAX_429_RETRIES + 1):
        try:
            resp = client.get(url, params=params, timeout=_REQUEST_TIMEOUT)
        except httpx.TimeoutException:
            if attempt >= _MAX_429_RETRIES:
                raise
            sleep = _RETRY_TIMEOUT_SLEEP * (2 ** attempt)
            log.warning(
                "TMDB request timed out, retrying",
                extra={"path": path, "attempt": attempt, "sleep_for": sleep},
            )
            time.sleep(sleep)
            continue
        if resp.status_code == 404:
            return None
        if resp.status_code == 429:
            if attempt >= _MAX_429_RETRIES:
                raise httpx.HTTPStatusError(
                    f"TMDB 429 after {attempt} retries for {path}",
                    request=resp.request,
                    response=resp,
                )
            log.warning(
                "rate-limited by TMDB",
                extra={"path": path, "attempt": attempt, "sleep_for": _RETRY_429_SLEEP},
            )
            time.sleep(_RETRY_429_SLEEP)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("unreachable")


def download_id_export(
    *,
    when: datetime | None = None,
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    """Download and decode the TMDB daily id export.

    Returns one dict per movie, each containing ``id``, ``original_title``,
    ``popularity``, ``video``, ``adult``.
    """
    when = when or datetime.now(timezone.utc)
    url = _export_url(when)
    log.info("downloading TMDB id export", extra={"url": url})
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
    with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as gz:
        rows = [json.loads(line) for line in gz if line.strip()]
    log.info("id export decoded", extra={"rows": len(rows)})
    return rows


def filter_export(
    rows: list[dict[str, Any]],
    *,
    min_popularity: float = 1.0,
) -> list[int]:
    """Drop adult titles and the unpopular long tail; return the surviving ids."""
    kept = [
        int(r["id"])
        for r in rows
        if not r.get("adult", False) and float(r.get("popularity", 0.0)) >= min_popularity
    ]
    log.info(
        "id export filtered",
        extra={"before": len(rows), "after": len(kept), "min_popularity": min_popularity},
    )
    return kept


def fetch_movie(
    client: httpx.Client,
    api_key: str,
    movie_id: int,
) -> dict[str, Any] | None:
    """Fetch one movie record synchronously. Returns ``None`` for 404 / deleted.

    Args:
        client:   Shared ``httpx.Client`` instance.
        api_key:  TMDB v3 API key.
        movie_id: TMDB movie identifier.
    """
    params = {"api_key": api_key, "append_to_response": "credits,keywords,videos"}
    return _tmdb_get(client, f"movie/{movie_id}", params)


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
    params = {"api_key": api_key, "language": "en-US", "page": 1}
    data = _tmdb_get(client, f"movie/{movie_id}/reviews", params)
    if data is None:
        return movie_id, None
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
