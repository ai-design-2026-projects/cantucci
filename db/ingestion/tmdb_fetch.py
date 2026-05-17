"""Pure TMDB API client: daily id export + per-movie sync fetch.

This module is the only place in the repo that talks directly to the TMDB
API. It is consumed by ``db/scrape.py`` (the stage-1 local scraper); no
other code path should import from here.

The sync ``httpx.Client`` + thread-pool fan-out used by ``db.scrape`` is a
deliberate choice over the previous async implementation: TMDB's per-IP
throttling makes sustained high concurrency a liability, and the sync path
keeps the dependency surface and failure modes minimal.
"""
import gzip
import io
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

log = logging.getLogger(__name__)

_TMDB_API_BASE = "https://api.themoviedb.org/3"
_TMDB_EXPORTS_BASE = "http://files.tmdb.org/p/exports"
_REQUEST_TIMEOUT = 30.0
_RETRY_429_SLEEP = 10.0
_MAX_429_RETRIES = 3


def _export_url(when: datetime) -> str:
    """Return the daily id-export URL for *when* (UTC).

    The export file is published around 08:00 UTC, so callers before that
    hour are silently rolled back one day to a guaranteed-available file.
    """
    if when.hour < 8:
        when = when - timedelta(days=1)
    return f"{_TMDB_EXPORTS_BASE}/movie_ids_{when:%m_%d_%Y}.json.gz"


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

    429 handling: sleep ``_RETRY_429_SLEEP`` seconds and retry, up to
    ``_MAX_429_RETRIES`` times, then raise. Deliberately dumb — the right
    response to sustained throttling is to lower ``--concurrency``, not to
    layer a smarter limiter on top of an already-rate-limited path.
    """
    url = f"{_TMDB_API_BASE}/movie/{movie_id}"
    params = {"api_key": api_key, "append_to_response": "credits,keywords"}
    for attempt in range(_MAX_429_RETRIES + 1):
        resp = client.get(url, params=params, timeout=_REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        if resp.status_code == 429:
            if attempt >= _MAX_429_RETRIES:
                raise httpx.HTTPStatusError(
                    f"TMDB 429 after {attempt} retries for id {movie_id}",
                    request=resp.request,
                    response=resp,
                )
            log.warning(
                "rate-limited by TMDB",
                extra={"id": movie_id, "attempt": attempt, "sleep_for": _RETRY_429_SLEEP},
            )
            time.sleep(_RETRY_429_SLEEP)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("unreachable")
