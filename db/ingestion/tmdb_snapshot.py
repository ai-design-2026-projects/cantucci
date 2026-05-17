"""TMDB → cleaned DataFrame snapshot (Colab side of the ingestion pipeline).

This module is the **only** place that talks to the TMDB API. It is intended to
be invoked from ``notebooks/embed_in_colab.ipynb`` once per snapshot — never at
session time. The output DataFrame matches the schema produced by the legacy
Kaggle ``clean.prepare()`` function, so ``split.three_way`` and ``load.ingest``
consume it unchanged.

Snapshot algorithm:
    1. Download the TMDB daily ID export (gzipped JSONL, one row per movie id).
    2. Pre-filter on the lightweight fields included in the export
       (``adult == False`` and ``popularity >= 1``).
    3. Fetch ``/movie/{id}?append_to_response=credits,keywords`` for each id,
       concurrently with a bounded semaphore.
    4. Post-filter on ``vote_count >= min_vote_count`` (default 5).
    5. Map each response into the cleaned-shape row dict, compute
       ``composite_text`` and ``bayesian_rating``, and return one DataFrame.
"""
import asyncio
import gzip
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pandas as pd

from backend.settings import get_env

log = logging.getLogger(__name__)

_TMDB_API_BASE = "https://api.themoviedb.org/3"
_TMDB_EXPORTS_BASE = "http://files.tmdb.org/p/exports"
_DEFAULT_CONCURRENCY = 20
_DEFAULT_RATE_PER_SEC = 30.0
_MAX_429_RETRIES = 5
_MAX_BACKOFF_SECONDS = 60.0
_BAYESIAN_PRIOR_VOTES = 50


class _AsyncRateLimiter:
    """Async token-bucket rate limiter shared across coroutines.

    Refills ``rate_per_sec`` tokens per second up to a burst cap of one
    second's worth. ``acquire()`` consumes one token, sleeping just long
    enough for the next token to materialise when the bucket is empty.
    A single lock serialises the read-modify-write on the bucket state so
    the global rate holds even with hundreds of concurrent waiters.
    """

    def __init__(self, rate_per_sec: float) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        self._rate = rate_per_sec
        self._tokens = rate_per_sec
        self._last = asyncio.get_event_loop().time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until one token is available, then consume it."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


def _run_async(coro: Any) -> Any:
    """Run *coro* to completion from sync code, even inside a running loop.

    ``asyncio.run`` raises when called from a thread that already has an active
    event loop, which is the default state in Jupyter / Colab. To keep the
    snapshot callable from both plain scripts and notebooks, fall back to
    executing the coroutine on a fresh loop in a worker thread when a loop is
    already running on this thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import threading

    result: dict[str, Any] = {}

    def _runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            result["value"] = loop.run_until_complete(coro)
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller's thread
            result["error"] = exc
        finally:
            loop.close()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result["value"]


def _export_url(when: datetime) -> str:
    """Return the daily ID export URL for *when* (UTC).

    The export file is published around 08:00 UTC, so callers before that hour
    are silently rolled back one day to a guaranteed-available file.
    """
    if when.hour < 8:
        when = when - timedelta(days=1)
    return f"{_TMDB_EXPORTS_BASE}/movie_ids_{when:%m_%d_%Y}.json.gz"


def _download_id_export(
    *,
    when: datetime | None = None,
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    """Download and decode the daily ID export. Returns one dict per movie.

    Each dict contains: ``id``, ``original_title``, ``popularity``,
    ``video``, ``adult``.
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


def _filter_export(
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


async def _fetch_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    limiter: _AsyncRateLimiter,
    api_key: str,
    movie_id: int,
    *,
    attempt: int = 0,
) -> dict[str, Any] | None:
    """Fetch a single movie's full record. Returns None on 404 / deleted.

    Rate-limit handling: 429 responses honour ``Retry-After`` and back off
    exponentially (``2 ** attempt``, capped at ``_MAX_BACKOFF_SECONDS``).
    After ``_MAX_429_RETRIES`` failed attempts the call raises rather than
    silently dropping the id, per the project's fail-loudly policy.
    """
    params = {"api_key": api_key, "append_to_response": "credits,keywords"}
    await limiter.acquire()
    async with sem:
        resp = await client.get(
            f"{_TMDB_API_BASE}/movie/{movie_id}",
            params=params,
            timeout=30.0,
        )
    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        if attempt >= _MAX_429_RETRIES:
            raise httpx.HTTPStatusError(
                f"TMDB 429 after {attempt} retries for id {movie_id}",
                request=resp.request,
                response=resp,
            )
        retry_after = float(resp.headers.get("retry-after", "1"))
        sleep_for = min(_MAX_BACKOFF_SECONDS, max(retry_after, 2 ** attempt))
        log.warning(
            "rate-limited by TMDB",
            extra={"id": movie_id, "attempt": attempt, "sleep_for": sleep_for},
        )
        await asyncio.sleep(sleep_for)
        return await _fetch_one(
            client, sem, limiter, api_key, movie_id, attempt=attempt + 1
        )
    resp.raise_for_status()
    return resp.json()


async def _fetch_all(
    ids: list[int],
    *,
    api_key: str,
    concurrency: int,
    rate_per_sec: float = _DEFAULT_RATE_PER_SEC,
    progress_every: int = 1000,
) -> list[dict[str, Any]]:
    """Fan out one request per id with bounded concurrency and a global rate cap."""
    sem = asyncio.Semaphore(concurrency)
    limiter = _AsyncRateLimiter(rate_per_sec)
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(http2=False) as client:
        tasks = [
            asyncio.create_task(_fetch_one(client, sem, limiter, api_key, mid))
            for mid in ids
        ]
        for i, task in enumerate(asyncio.as_completed(tasks), start=1):
            record = await task
            if record is not None:
                results.append(record)
            if i % progress_every == 0:
                log.info("tmdb fetch progress", extra={"done": i, "total": len(ids)})
    log.info("tmdb fetch complete", extra={"requested": len(ids), "got": len(results)})
    return results


def _top3_cast(cast_list: list[dict[str, Any]]) -> list[str]:
    """Top 3 cast names by billing order."""
    sorted_cast = sorted(cast_list, key=lambda c: c.get("order", 999))
    return [c["name"] for c in sorted_cast[:3] if "name" in c]


def _director(crew_list: list[dict[str, Any]]) -> str:
    """First crew member with job == Director, else ''."""
    for c in crew_list:
        if c.get("job") == "Director" and "name" in c:
            return c["name"]
    return ""


def _composite_text(row: dict[str, Any]) -> str:
    """Concatenate the high-signal text fields used for embedding.

    Mirrors the formula from the legacy ``db/ingestion/clean.py`` — title,
    original_title (if different), release year, genres, tagline, overview,
    top-3 cast, director, and keyword names.
    """
    parts: list[str] = []
    title = (row.get("title") or "").strip()
    original_title = (row.get("original_title") or "").strip()
    parts.append(title)
    if original_title and original_title.lower() != title.lower():
        parts.append(original_title)

    year = row.get("release_year")
    if year:
        parts.append(str(int(year)))

    parts.append(" ".join(g.get("name", "") for g in (row.get("genres") or [])))
    parts.append((row.get("tagline") or "").strip())
    parts.append((row.get("overview") or "").strip())
    parts.append(" ".join(row.get("top3_cast") or []))
    parts.append(row.get("director") or "")
    parts.append(" ".join(k.get("name", "") for k in (row.get("keywords") or [])))

    return " ".join(p for p in (str(p).strip() for p in parts) if p)


def _map_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Map a raw TMDB JSON response into the cleaned-shape row dict.

    Output keys match what ``db/ingestion/load.py`` and ``split.three_way``
    consume — same shape as the legacy ``clean.prepare()`` rows.
    """
    cast = list((rec.get("credits") or {}).get("cast") or [])
    crew = list((rec.get("credits") or {}).get("crew") or [])
    keywords = list((rec.get("keywords") or {}).get("keywords") or [])

    release_date = rec.get("release_date") or None
    if release_date == "":
        release_date = None
    release_year: int | None = None
    if release_date:
        try:
            release_year = int(release_date[:4])
        except ValueError:
            release_year = None

    budget = rec.get("budget")
    revenue = rec.get("revenue")
    row: dict[str, Any] = {
        "id": int(rec["id"]),
        "imdb_id": rec.get("imdb_id") or None,
        "title": rec.get("title") or rec.get("original_title") or "",
        "original_title": rec.get("original_title") or "",
        "original_language": rec.get("original_language") or None,
        "overview": rec.get("overview") or None,
        "tagline": rec.get("tagline") or None,
        "release_date": release_date,
        "release_year": release_year,
        "runtime": rec.get("runtime"),
        # Zero budget/revenue are the TMDB convention for "missing" — drop to NaN
        # so the bayesian_rating + downstream stats don't get poisoned.
        "budget": (budget if budget else None),
        "revenue": (revenue if revenue else None),
        "popularity": rec.get("popularity"),
        "vote_average": rec.get("vote_average"),
        "vote_count": rec.get("vote_count"),
        "status": rec.get("status") or None,
        "adult": bool(rec.get("adult", False)),
        "video": bool(rec.get("video", False)),
        "poster_path": rec.get("poster_path") or None,
        "homepage": rec.get("homepage") or None,
        "belongs_to_collection": rec.get("belongs_to_collection") or None,
        "genres": rec.get("genres") or [],
        "production_companies": rec.get("production_companies") or [],
        "production_countries": rec.get("production_countries") or [],
        "spoken_languages": rec.get("spoken_languages") or [],
        "cast": cast,
        "crew": crew,
        "keywords": keywords,
    }
    row["top3_cast"] = _top3_cast(cast)
    row["director"] = _director(crew)
    return row


def _build_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Map raw TMDB JSONs → cleaned DataFrame with composite_text + bayesian_rating."""
    rows = [_map_record(r) for r in records]
    df = pd.DataFrame(rows)

    df["vote_count"] = pd.to_numeric(df["vote_count"], errors="coerce")
    df["vote_average"] = pd.to_numeric(df["vote_average"], errors="coerce")
    vc = df["vote_count"].fillna(0)
    va = df["vote_average"].fillna(0)
    # Vote-count-weighted mean as the Bayesian prior, matching the legacy formula.
    prior_mean = float((va * vc).sum() / vc.sum()) if vc.sum() > 0 else 0.0
    m = _BAYESIAN_PRIOR_VOTES
    df["bayesian_rating"] = (vc * va + m * prior_mean) / (vc + m)

    df["composite_text"] = df.apply(_composite_text, axis=1)

    assert df["id"].isna().sum() == 0, "NaN ids in snapshot"
    assert df["id"].is_unique, "Duplicate ids in snapshot"
    assert (df["composite_text"].str.strip() == "").sum() == 0, "Empty composite_text in snapshot"
    return df.reset_index(drop=True)


def snapshot(
    *,
    api_key: str | None = None,
    min_vote_count: int = 5,
    min_popularity: float = 1.0,
    concurrency: int = _DEFAULT_CONCURRENCY,
    rate_per_sec: float = _DEFAULT_RATE_PER_SEC,
    limit: int | None = None,
) -> pd.DataFrame:
    """Produce a fresh TMDB catalogue snapshot as a cleaned DataFrame.

    Args:
        api_key:         TMDB v3 API key. Falls back to the ``TMDB_API_KEY`` env var.
        min_vote_count:  Drop films with fewer than this many TMDB votes.
                         Filters out the long obscure tail; 5 is a good default.
        min_popularity:  Pre-filter on the export's ``popularity`` field before
                         spending any per-movie requests.
        concurrency:     Max concurrent in-flight requests to ``/movie/{id}``.
        rate_per_sec:    Global token-bucket cap on outbound requests, shared
                         across all coroutines. TMDB throttles around 50 req/s
                         per IP; the default of 30 leaves headroom for retries.
        limit:           Optional cap for dry runs (e.g. 1000). Production
                         snapshots leave this at None.

    Returns:
        DataFrame matching the schema consumed by ``db/ingestion/split.three_way``
        and ``db/ingestion/load.ingest`` (modulo embeddings, which are added by
        the embedding step in the Colab notebook).
    """
    resolved_key = api_key or get_env().tmdb_api_key
    if not resolved_key:
        raise ValueError(
            "TMDB API key required. Set TMDB_API_KEY in the environment or "
            "pass api_key= explicitly."
        )

    export = _download_id_export()
    ids = _filter_export(export, min_popularity=min_popularity)
    if limit is not None:
        ids = ids[:limit]
        log.info("dry-run limit applied", extra={"limit": limit})

    records = _run_async(
        _fetch_all(
            ids,
            api_key=resolved_key,
            concurrency=concurrency,
            rate_per_sec=rate_per_sec,
        )
    )

    kept = [r for r in records if (r.get("vote_count") or 0) >= min_vote_count]
    log.info(
        "vote_count filter applied",
        extra={"before": len(records), "after": len(kept), "min_vote_count": min_vote_count},
    )

    df = _build_dataframe(kept)
    log.info("snapshot built", extra={"rows": len(df)})
    return df
