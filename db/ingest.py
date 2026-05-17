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
"""
import argparse
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


def _load_artifact(path: Path) -> tuple[pd.DataFrame, np.ndarray]:
    """Load a parquet artifact; return (df, embeddings) with the embedding column removed."""
    df = pd.read_parquet(path)
    embeddings = np.array(df.pop("embedding").tolist(), dtype=np.float32)
    for col in _NESTED_COLS:
        if col in df.columns:
            df[col] = df[col].apply(json.loads)
    return df, embeddings


def run_from_artifact(name: str) -> None:
    """Fetch the pinned HF artifact(s) and ingest into the DB.

    Args:
        name: Which artifact(s) to ingest — ``"main"``, ``"mini"``, or ``"all"`` (main + mini).

    Raises:
        ValueError: If *name* is ``"eval"`` — eval_holdout is never ingested by design.
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
        df, embeddings = _load_artifact(local_path)
        load.ingest(df, embeddings)


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
    return p.parse_args()


def main() -> None:
    """CLI entry point."""
    configure_logging()
    args = _parse_args()
    run_from_artifact(args.set)


if __name__ == "__main__":
    main()
