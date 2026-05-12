"""CinePal catalogue ingestion pipeline.

Usage:
    python -m db.ingest                      # full pipeline (download → clean → embed → ingest)
    python -m db.ingest --no-download        # skip Kaggle download, use existing data/raw/
    python -m db.ingest --no-ingest          # produce artifacts only, skip DB writes
    python -m db.ingest --ingest mini        # ingest the mini artifact (fast, for dev/CI)
    python -m db.ingest --mini-size 200 --eval-frac 0.10 --seed 42
    python -m db.ingest --model sentence-transformers/all-MiniLM-L6-v2

Artifacts produced under data/artifacts/:
    main.parquet         — full training set with embeddings
    mini.parquet         — small popular-movies subset (fast to load, reusable in CI)
    eval_holdout.parquet — disjoint evaluation slice (never ingested into the DB)
"""
import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from backend.logging import configure_logging
from db.ingestion import clean, download, embed, load, split

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_RAW_DIR = _ROOT / "data" / "raw"
_ARTIFACTS_DIR = _ROOT / "data" / "artifacts"
_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Columns with nested Python objects that need JSON escaping for parquet compat.
_NESTED_COLS = (
    "genres", "cast", "crew", "keywords",
    "production_companies", "production_countries", "spoken_languages",
    "belongs_to_collection", "top3_cast", "director",
)


def _save(df: pd.DataFrame, embeddings: np.ndarray, path: Path) -> None:
    """Persist *df* with an embedding column to a parquet file.

    Nested list/dict columns are JSON-encoded so pyarrow can serialise them
    reliably; _load_artifact reverses this.
    """
    out = df.copy()
    out["embedding"] = [arr.tolist() for arr in embeddings]
    for col in _NESTED_COLS:
        if col in out.columns:
            out[col] = out[col].apply(json.dumps)
    out.to_parquet(path, index=False)
    log.info("artifact saved", extra={"path": str(path), "rows": len(out)})


def _load_artifact(path: Path) -> tuple[pd.DataFrame, np.ndarray]:
    """Load a parquet artifact; return (df, embeddings) with the embedding column removed."""
    df = pd.read_parquet(path)
    embeddings = np.array(df.pop("embedding").tolist(), dtype=np.float32)
    for col in _NESTED_COLS:
        if col in df.columns:
            df[col] = df[col].apply(json.loads)
    return df, embeddings


def run_full(args: argparse.Namespace) -> None:
    """Download, clean, split, embed all three sets, save artifacts, ingest main."""
    _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    if not args.no_download:
        download.fetch(_RAW_DIR, force=args.force_download)

    df = clean.prepare(_RAW_DIR)
    main_df, mini_df, eval_df = split.three_way(
        df,
        mini_size=args.mini_size,
        eval_frac=args.eval_frac,
        seed=args.seed,
    )

    # Embed all three sets in one model-load pass
    all_texts = (
        list(main_df["composite_text"])
        + list(mini_df["composite_text"])
        + list(eval_df["composite_text"])
    )
    all_emb = embed.encode_all(all_texts, model_name=args.model, batch_size=args.embed_batch_size)

    n_main, n_mini = len(main_df), len(mini_df)
    main_emb = all_emb[:n_main]
    mini_emb = all_emb[n_main : n_main + n_mini]
    eval_emb = all_emb[n_main + n_mini :]

    _save(main_df, main_emb, _ARTIFACTS_DIR / "main.parquet")
    _save(mini_df, mini_emb, _ARTIFACTS_DIR / "mini.parquet")
    _save(eval_df, eval_emb, _ARTIFACTS_DIR / "eval_holdout.parquet")

    if not args.no_ingest:
        load.ingest(main_df, main_emb)


def run_mini(args: argparse.Namespace) -> None:
    """Ingest the pre-built mini artifact — fast path for dev/CI."""
    path = _ARTIFACTS_DIR / "mini.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Mini artifact not found at {path}.\n"
            "Run `python -m db.ingest --no-ingest` first to generate all artifacts."
        )
    df, embeddings = _load_artifact(path)
    load.ingest(df, embeddings)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CinePal catalogue ingestion pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--ingest", choices=["main", "mini"], default="main",
        help="Which set to write to the DB. 'mini' loads a pre-built artifact (default: main).",
    )
    p.add_argument("--no-download", action="store_true",
                   help="Skip Kaggle download; reuse existing data/raw/.")
    p.add_argument("--force-download", action="store_true",
                   help="Re-download even if raw data is already present.")
    p.add_argument("--no-ingest", action="store_true",
                   help="Produce artifacts only; skip all DB writes.")
    p.add_argument("--mini-size", type=int, default=200, metavar="N",
                   help="Number of movies in the mini set (default: 200).")
    p.add_argument("--eval-frac", type=float, default=0.10, metavar="F",
                   help="Fraction of the dataset held out for evaluation (default: 0.10).")
    p.add_argument("--seed", type=int, default=42,
                   help="Random seed for reproducible splits (default: 42).")
    p.add_argument("--embed-batch-size", type=int, default=256, metavar="B",
                   help="Sentence-transformer encoding batch size (default: 256).")
    p.add_argument("--model", default=_DEFAULT_MODEL,
                   help=f"Embedding model name (default: {_DEFAULT_MODEL}).")
    return p.parse_args()


def main() -> None:
    """CLI entry point."""
    configure_logging()
    args = _parse_args()

    if args.ingest == "mini":
        if args.no_ingest:
            log.warning("--no-ingest has no effect when --ingest mini is used")
        run_mini(args)
    else:
        run_full(args)


if __name__ == "__main__":
    main()
