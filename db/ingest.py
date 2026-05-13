"""
CinePal catalogue ingestion pipeline.
Usage:
    python -m db.ingest                                  # full pipeline (download → clean → embed → ingest)
    python -m db.ingest --no-download                    # skip Kaggle download, use existing data/raw/
    python -m db.ingest --no-ingest                      # produce artifacts only, skip DB writes
    python -m db.ingest --ingest mini                    # ingest the mini artifact (fast, for dev/CI)
    python -m db.ingestion.fetch                         # download pre-built artifacts from Hugging Face
    python -m db.ingest --ingest main --from-artifact    # ingest main set from pre-built artifact
    python -m db.ingest --ingest all --from-artifact     # ingest main + mini from pre-built artifacts
    python -m db.ingest --mini-size 200 --eval-frac 0.10 --seed 42

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

from backend.logging_setup import configure_logging
from backend.settings import ARTIFACTS_DIR, RAW_DATA_DIR, get_settings
from db.ingestion import clean, download, embed, load, split

log = logging.getLogger(__name__)

# Columns with nested Python objects that need JSON escaping for parquet compat.
_NESTED_COLS = (
    "genres", "cast", "crew", "keywords",
    "production_companies", "production_countries", "spoken_languages",
    "belongs_to_collection", "top3_cast", "director",
)


def _save(df: pd.DataFrame, embeddings: np.ndarray, path: Path) -> None:
    """Persist *df* with an embedding column to a parquet file.

    Nested list/dict columns are JSON-encoded so pyarrow can serialise them
    reliably,
    """
    out = df.copy()
    # Add the embedding column
    out["embedding"] = [arr.tolist() for arr in embeddings]
    for col in _NESTED_COLS:
        if col in out.columns:
            out[col] = out[col].apply(json.dumps)
    # Write to parquet
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


def run_from_artifact(name: str) -> None:
    """Ingest pre-built parquet artifact(s) without running the embedding pipeline.

    Args:
        name: Which artifact(s) to ingest — "main", "mini", or "all" (main + mini).

    Raises:
        FileNotFoundError: If the requested parquet file does not exist under
            data/artifacts/. Run `python -m db.ingestion.fetch` to download it.
        ValueError: If *name* is "eval" — eval_holdout is never ingested by design.
    """
    if name == "eval":
        raise ValueError(
            "eval_holdout is intentionally kept out of the DB — "
            "use it only for offline evaluation."
        )
    names = ["main", "mini"] if name == "all" else [name]
    for n in names:
        path = ARTIFACTS_DIR / f"{n}.parquet"
        if not path.exists():
            raise FileNotFoundError(
                f"Artifact not found at {path}.\n"
                "Run `python -m db.ingestion.fetch` to download pre-built artifacts,\n"
                "or `python -m db.ingest --no-ingest` to build them locally."
            )
        df, embeddings = _load_artifact(path)
        load.ingest(df, embeddings)


def run_full(args: argparse.Namespace) -> None:
    """Download, clean, split, embed all three sets, save artifacts, optionally ingest."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    representation = get_settings().representation

    if not args.no_download:
        download.fetch(RAW_DATA_DIR, force=args.force_download)

    df = clean.prepare(RAW_DATA_DIR)
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
    all_emb = embed.encode_all(
        all_texts,
        model_name=representation.model,
        expected_dim=representation.embedding_dim,
        batch_size=args.embed_batch_size,
    )

    n_main, n_mini = len(main_df), len(mini_df)
    main_emb = all_emb[:n_main]
    mini_emb = all_emb[n_main : n_main + n_mini]
    eval_emb = all_emb[n_main + n_mini :]

    _save(main_df, main_emb, ARTIFACTS_DIR / "main.parquet")
    _save(mini_df, mini_emb, ARTIFACTS_DIR / "mini.parquet")
    _save(eval_df, eval_emb, ARTIFACTS_DIR / "eval_holdout.parquet")

    if not args.no_ingest:
        names = ["main", "mini"] if args.ingest == "all" else [args.ingest]
        dfs = {"main": main_df, "mini": mini_df}
        embs = {"main": main_emb, "mini": mini_emb}
        for n in names:
            load.ingest(dfs[n], embs[n])


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CinePal catalogue ingestion pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--ingest", choices=["main", "mini", "all"], default="main",
        help="Which set(s) to write to the DB (default: main).",
    )
    p.add_argument(
        "--from-artifact", action="store_true",
        help="Load from pre-built parquet artifacts; skip download, clean, embed.",
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
    return p.parse_args()


def main() -> None:
    """CLI entry point."""
    configure_logging()
    args = _parse_args()

    use_artifact = args.from_artifact or args.ingest == "mini"
    if use_artifact:
        if args.no_ingest:
            log.warning("--no-ingest has no effect when loading from an artifact")
        run_from_artifact(args.ingest)
    else:
        run_full(args)


if __name__ == "__main__":
    main()
