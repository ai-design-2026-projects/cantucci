"""
CinePal catalogue scrape — stage 1 of the ingestion pipeline.

Pulls the TMDB daily id export, fetches ``/movie/{id}?append_to_response=credits,keywords``
for each surviving id, builds the cleaned-schema parquet, and (optionally) uploads
it to the HF dataset repo under ``snapshots/``. The Colab embedding notebook then
downloads that snapshot, splits, embeds, and writes the three parquets under
``embeddings/``.

This split exists because TMDB throttles by IP and Colab's shared egress IPs make
sustained scraping unreliable; running the scrape from a developer's home IP
sidesteps the issue entirely.

Usage:
    export TMDB_API_KEY=...
    python -m dataset.scrape.scraper --limit 500 --concurrency 5   # local smoke
    python -m dataset.scrape.scraper                               # full local run, no upload
    python -m dataset.scrape.scraper --upload                      # full local run + push to HF

Re-runs of the same command resume from ``data/local_scrape/tmdb_raw.jsonl``,
so a crash mid-run loses at most the in-flight requests.
"""
import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from tqdm.auto import tqdm

from backend.logging_setup import configure_logging
from backend.settings import get_env, get_settings
from dataset.io import upload
from dataset.scrape import tmdb_fetch
from dataset.scrape import clean

log = logging.getLogger(__name__)

_DEFAULT_CONCURRENCY = 8
_DEFAULT_MIN_VOTE_COUNT = 10
_DEFAULT_MIN_POPULARITY = 5
_DEFAULT_OUTPUT_DIR = Path("data/local_scrape")


def _already_fetched(jsonl_path: Path) -> set[int]:
    """Return the set of TMDB ids already present in *jsonl_path*.

    Enables idempotent re-runs: the scraper subtracts this set from the
    candidate id list and only fetches what's missing. Empty set if the
    file doesn't exist yet.
    """
    if not jsonl_path.exists():
        return set()
    seen: set[int] = set()
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            seen.add(int(rec["id"]))
    return seen


def _scrape(
    api_key: str,
    ids: list[int],
    jsonl_path: Path,
    concurrency: int,
) -> int:
    """Fetch every id in *ids* and stream raw JSON responses into *jsonl_path*.

    Returns the number of records appended. The file is opened in line-buffered
    append mode so each completed fetch is flushed to disk — a crash mid-run
    loses at most the in-flight requests.
    """
    if not ids:
        return 0
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    ok = 0
    with (
        httpx.Client(timeout=30.0) as client,
        jsonl_path.open("a", encoding="utf-8", buffering=1) as fh,
        ThreadPoolExecutor(max_workers=concurrency) as pool,
        tqdm(total=len(ids), desc="TMDB scrape", unit="movie") as bar,
    ):
        futures = {pool.submit(tmdb_fetch.fetch_movie, client, api_key, mid): mid for mid in ids}
        for fut in as_completed(futures):
            rec = fut.result()
            if rec is not None:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                ok += 1
            bar.update(1)
            elapsed = time.monotonic() - t0
            rps = bar.n / elapsed if elapsed > 0 else 0.0
            bar.set_postfix(ok=ok, rps=f"{rps:.1f}/s")
    return ok


def _read_jsonl(jsonl_path: Path) -> list[dict[str, Any]]:
    """Load every record from a JSONL file into a list of dicts."""
    records: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CinePal catalogue scrape — TMDB → cleaned parquet (+ optional HF upload)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--limit", type=int, default=None, help="Cap on number of ids to fetch (default: full export).")
    p.add_argument("--concurrency", type=int, default=_DEFAULT_CONCURRENCY)
    p.add_argument("--min-vote-count", type=int, default=_DEFAULT_MIN_VOTE_COUNT,
                   help="Drop films with fewer TMDB votes than this from the final parquet.")
    p.add_argument("--min-popularity", type=float, default=_DEFAULT_MIN_POPULARITY,
                   help="Pre-filter on the export's popularity field before fetching.")
    p.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    p.add_argument("--api-key", default=get_env().tmdb_api_key or None,
                   help="TMDB v3 API key (falls back to TMDB_API_KEY env var).")
    p.add_argument("--upload", action="store_true",
                   help="Upload the final parquet to the HF dataset repo under snapshots/.")
    p.add_argument("--repo-id", default=None,
                   help="HF repo id for --upload. Defaults to ingestion.hf_repo from configs/default.yaml.")
    p.add_argument("--skip-reviews", action="store_true",
                   help="Skip TMDB review fetching (faster; produces NULL reviews_text).")
    return p.parse_args()


def main() -> None:
    """CLI entry point — see module docstring."""
    configure_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # If no API key for TMDB is provided, abort immediately
    args = _parse_args()
    if not args.api_key:
        raise SystemExit("TMDB API key required: set TMDB_API_KEY or pass --api-key")

    # Paths for the raw JSONL export and the cleaned parquet snapshot
    jsonl_path = args.output_dir / "tmdb_raw.jsonl"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    parquet_path = args.output_dir / f"snapshot_{stamp}.parquet"

    # Fetch the TMDB id export, filter it down to our candidates
    export = tmdb_fetch.download_id_export()
    candidate_ids = tmdb_fetch.filter_export(export, min_popularity=args.min_popularity)
    if args.limit is not None:
        candidate_ids = candidate_ids[: args.limit]

    # Subract the ids we've already fetched and persisted in the JSONL file
    already_fetched = _already_fetched(jsonl_path)
    to_fetch = [movie_id for movie_id in candidate_ids if movie_id not in already_fetched]
    log.info(
        "scrape plan",
        extra={
            "candidates": len(candidate_ids),
            "already_fetched": len(already_fetched),
            "to_fetch": len(to_fetch),
        },
    )
    
    # Fetch the missing ids and append them to the JSONL file as we go
    if to_fetch:
        wrote = _scrape(args.api_key, to_fetch, jsonl_path, args.concurrency)
        log.info("scrape complete", extra={"appended": wrote})

    # Validate that we have some records to build a parquet from, otherwise abort instantly
    raw_records = _read_jsonl(jsonl_path)
    if not raw_records:
        raise SystemExit("no records on disk to build a parquet from")

    # For each movie record, fetch the reviews text
    fetched_reviews: dict[int, str] = {}
    if not args.skip_reviews:
        movie_ids = [int(r["id"]) for r in raw_records]
        fetched_reviews = tmdb_fetch.fetch_all_reviews(
            args.api_key,
            movie_ids,
            concurrency=args.concurrency,
        )
        log.info(
            "reviews_ready",
            extra={"with_reviews": len(fetched_reviews), "total": len(movie_ids)},
        )

    # Build the cleaned-schema dataframe, applying the vote_count filter, and write it out as parquet
    df = clean.build_dataframe(raw_records, reviews=fetched_reviews or None)
    before = len(df)
    df = df[df["vote_count"].fillna(0) >= args.min_vote_count].reset_index(drop=True)
    log.info(
        "vote_count filter applied",
        extra={"before": before, "after": len(df), "min_vote_count": args.min_vote_count},
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet_path, index=False)
    log.info("parquet written", extra={"rows": len(df), "path": str(parquet_path)})

    if args.upload:
        repo_id = args.repo_id or get_settings().ingestion.hf_repo
        path_in_repo = upload.upload_snapshot(parquet_path, repo_id=repo_id, timestamp=stamp)
        print(f"\nUploaded. Paste this into configs/default.yaml under ingestion.artifacts.snapshot:\n")
        print(f"  snapshot: {path_in_repo}")


if __name__ == "__main__":
    main()
