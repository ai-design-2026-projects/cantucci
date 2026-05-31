"""
CinePal catalogue ingestion — load pre-built parquet artifacts from HuggingFace.

Usage:
    python -m db.ingest                # ingest the mini set (dev default)
    python -m db.ingest --set main     # ingest the full production set
    python -m db.ingest --set eval     # ingest the eval-holdout set
    python -m db.ingest --set all      # ingest main + mini

The repo and per-split filenames are pinned in ``configs/dev.yaml`` under
the ``ingestion:`` block. Producing a new snapshot is a two-stage workflow:
``python -m dataset.scraper --upload`` (local TMDB scrape) followed by
``notebooks/embed_in_colab.ipynb`` (GPU embed + upload).

After all rows are loaded, the script computes fused embeddings and UMAP coordinates
directly from the in-memory embeddings and writes them to the movies table. No GPU
is required.
"""
import argparse
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.logging_setup import configure_logging
from backend.settings import get_settings
from db.utils import load
from dataset.hub.fetch import fetch_artifact
from dataset.transform.offline import compute_offline_columns

log = logging.getLogger(__name__)

_NESTED_COLS = (
    "genres", "cast", "crew", "keywords",
    "production_companies", "production_countries", "spoken_languages",
    "belongs_to_collection", "top3_cast", "director",
)


def _load_artifact(
    path: Path,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray | None, np.ndarray | None]:
    """Load a parquet artifact; return ``(df, text_embeddings, review_embeddings, trailer_embeddings)``.

    Handles both the new format (``text_embedding`` + optional ``review_embedding``
    and ``trailer_embedding`` columns) and the legacy format (single ``embedding``
    column treated as ``text_embedding``).

    Args:
        path: Local path to the parquet file.

    Returns:
        Tuple of ``(df, text_embeddings, review_embeddings, trailer_embeddings)``.
        ``review_embeddings`` is an all-zero array for rows without reviews, or
        ``None`` if no ``review_embedding`` column exists in the file.
        ``trailer_embeddings`` is an all-zero array for rows without trailers, or
        ``None`` if no ``trailer_embedding`` column exists in the file.

    Raises:
        ValueError: If the parquet has neither ``text_embedding`` nor
                    ``embedding`` columns.
    """
    df = pd.read_parquet(path)

    if "text_embedding" in df.columns:
        text_embeddings = np.array(df.pop("text_embedding").tolist(), dtype=np.float32)
    elif "embedding" in df.columns:
        text_embeddings = np.array(df.pop("embedding").tolist(), dtype=np.float32)
    else:
        raise ValueError(
            f"Parquet at {path} has no 'text_embedding' or 'embedding' column"
        )

    dim = text_embeddings.shape[1]

    review_embeddings: np.ndarray | None = None
    if "review_embedding" in df.columns:
        rev_series = df.pop("review_embedding")
        review_array = np.zeros((len(df), dim), dtype=np.float32)
        for i, val in enumerate(rev_series):
            if val is not None:
                review_array[i] = np.array(val, dtype=np.float32)
        review_embeddings = review_array

    trailer_embeddings: np.ndarray | None = None
    if "trailer_embedding" in df.columns:
        trailer_series = df.pop("trailer_embedding")
        trailer_array = np.zeros((len(df), dim), dtype=np.float32)
        for i, val in enumerate(trailer_series):
            if val is not None:
                trailer_array[i] = np.array(val, dtype=np.float32)
        trailer_embeddings = trailer_array

    for col in _NESTED_COLS:
        if col in df.columns:
            df[col] = df[col].apply(json.loads)
    return df, text_embeddings, review_embeddings, trailer_embeddings


def run_from_artifact(name: str) -> None:
    """Fetch the pinned HF artifact(s) and ingest into the DB.

    After loading all rows, computes fused embeddings and UMAP coordinates from
    the in-memory embeddings and writes them to the movies table. Movies from
    multiple sets are deduplicated by ID before the offline computation runs.

    Args:
        name: Which artifact(s) to ingest — ``"main"``, ``"mini"``, ``"eval"``,
              ``"eval_holdout"``, or ``"all"`` (main + mini).
    """
    cfg = get_settings()
    filenames = {
        "main": cfg.ingestion.artifacts.main,
        "mini": cfg.ingestion.artifacts.mini,
        "eval_holdout": cfg.ingestion.artifacts.eval_holdout,
    }
    if name == "eval":
        name = "eval_holdout"
    names = ["main", "mini"] if name == "all" else [name]

    all_movie_ids: list[int] = []
    all_text_embs: list[np.ndarray] = []
    all_review_embs: list[np.ndarray] = []
    has_any_review = False
    seen_ids: set[int] = set()

    for n in names:
        local_path = fetch_artifact(cfg.ingestion.hf_repo, filenames[n])
        df, text_embeddings, review_embeddings, trailer_embeddings = _load_artifact(local_path)
        load.ingest(df, text_embeddings, review_embeddings, trailer_embeddings)

        dim = text_embeddings.shape[1]
        for i, mid in enumerate(df["id"].tolist()):
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            all_movie_ids.append(mid)
            all_text_embs.append(text_embeddings[i])
            if review_embeddings is not None:
                all_review_embs.append(review_embeddings[i])
                has_any_review = True
            else:
                all_review_embs.append(np.zeros(dim, dtype=np.float32))

    text_arr = np.stack(all_text_embs)
    review_arr = np.stack(all_review_embs) if has_any_review else None

    log.info("offline_pipeline_start", extra={"n_movies": len(all_movie_ids)})
    result = compute_offline_columns(all_movie_ids, text_arr, review_arr)

    load.upsert_offline_columns(all_movie_ids, result.umap_coords)
    log.info("ingest_complete", extra={"n_movies": len(all_movie_ids)})


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CinePal catalogue ingestion — HF parquet → Postgres",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
           "--set", choices=["mini", "main", "eval", "eval_holdout", "all"], default="mini",
        dest="set",
        help="Which set(s) to write to the DB (default: mini). "
               "mini is a strict subset of main — ingesting main later won't duplicate rows. "
               "eval and eval_holdout point at the held-out evaluation split.",
    )
    return p.parse_args()


def main() -> None:
    """CLI entry point."""
    configure_logging()
    args = _parse_args()
    run_from_artifact(args.set)


if __name__ == "__main__":
    main()
