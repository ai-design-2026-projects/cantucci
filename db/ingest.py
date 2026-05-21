"""
CinePal catalogue ingestion — load pre-built parquet artifacts from HuggingFace.

Usage:
    python -m db.ingest                # ingest the mini set (dev default)
    python -m db.ingest --set main     # ingest the full production set
    python -m db.ingest --set all      # ingest main + mini

The repo and per-split filenames are pinned in ``configs/default.yaml`` under
the ``ingestion:`` block. Producing a new snapshot is a two-stage workflow:
``python -m db.scrape --upload`` (local TMDB scrape) followed by
``notebooks/embed_in_colab.ipynb`` (GPU embed + upload). The ``eval_holdout``
slice is intentionally never written to the DB.

After all rows are loaded the script builds the base HDBSCAN cluster snapshot and
persists it as the root node of the cluster snapshot graph.  Re-running the script
will create a second root cluster snapshot — call with ``--skip-clustering`` during
development to skip that step.
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from backend.logging_setup import configure_logging
from backend.settings import get_settings
from db.ingestion import load
from db.ingestion.fetch import fetch_artifact

log = logging.getLogger(__name__)

_NESTED_COLS = (
    "genres", "cast", "crew", "keywords",
    "production_companies", "production_countries", "spoken_languages",
    "belongs_to_collection", "top3_cast", "director",
)


def _load_artifact(path: Path) -> tuple[pd.DataFrame, np.ndarray, np.ndarray | None]:
    """Load a parquet artifact; return ``(df, text_embeddings, review_embeddings)``.

    Handles both the new format (``text_embedding`` + optional ``review_embedding``
    columns) and the legacy format (single ``embedding`` column treated as
    ``text_embedding``).

    Args:
        path: Local path to the parquet file.

    Returns:
        Tuple of ``(df, text_embeddings, review_embeddings)`` where
        ``review_embeddings`` is an all-zero array for rows without reviews,
        or ``None`` if no ``review_embedding`` column exists in the file.

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

    review_embeddings: np.ndarray | None = None
    if "review_embedding" in df.columns:
        rev_series = df.pop("review_embedding")
        dim = text_embeddings.shape[1]
        review_array = np.zeros((len(df), dim), dtype=np.float32)
        for i, val in enumerate(rev_series):
            if val is not None:
                review_array[i] = np.array(val, dtype=np.float32)
        review_embeddings = review_array

    for col in _NESTED_COLS:
        if col in df.columns:
            df[col] = df[col].apply(json.loads)
    return df, text_embeddings, review_embeddings


def run_from_artifact(name: str, skip_clustering: bool = False) -> None:
    """Fetch the pinned HF artifact(s) and ingest into the DB.

    After loading all rows the base HDBSCAN cluster snapshot is computed unless
    *skip_clustering* is True.

    Args:
        name:             Which artifact(s) to ingest — ``"main"``,
                          ``"mini"``, or ``"all"`` (main + mini).
        skip_clustering:  When True, skip ``build_root_cluster_snapshot`` after load.

    Raises:
        ValueError: If *name* is ``"eval"`` — eval_holdout is never ingested.
    """
    if name == "eval":
        raise ValueError(
            "eval_holdout is intentionally kept out of the DB — "
            "use it only for offline evaluation."
        )
    cfg = get_settings().ingestion
    filenames = {
        "main": cfg.artifacts.main,
        "mini": cfg.artifacts.mini,
    }
    names = ["main", "mini"] if name == "all" else [name]
    for n in names:
        local_path = fetch_artifact(cfg.hf_repo, filenames[n])
        df, text_embeddings, review_embeddings = _load_artifact(local_path)
        load.ingest(df, text_embeddings, review_embeddings)

    if not skip_clustering:
        from backend.cluster_engine.offline import build_root_cluster_snapshot
        seed = get_settings().split.seed
        log.info("building_root_cluster_snapshot", extra={"seed": seed})
        asyncio.run(build_root_cluster_snapshot(seed))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CinePal catalogue ingestion — HF parquet → Postgres",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--set", choices=["mini", "main", "all"], default="mini",
        dest="set",
        help="Which set(s) to write to the DB (default: mini). "
             "mini is a strict subset of main — ingesting main later won't duplicate rows.",
    )
    p.add_argument(
        "--skip-clustering", action="store_true",
        help="Skip the HDBSCAN base cluster snapshot step (useful during dev).",
    )
    return p.parse_args()


def main() -> None:
    """CLI entry point."""
    configure_logging()
    args = _parse_args()
    run_from_artifact(args.set, skip_clustering=args.skip_clustering)


if __name__ == "__main__":
    main()
