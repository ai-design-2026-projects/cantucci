"""
CinePal catalogue ingestion pipeline.

Usage:
    python -m db.ingest                              # HF download → ingest mini (default)
    python -m db.ingest --set main                   # HF download → ingest full production set
    python -m db.ingest --set all                    # HF download → ingest main + mini
    python -m db.ingest --source local               # use existing artifacts → ingest mini
    python -m db.ingest --source local --set main
    python -m db.ingest --source kaggle              # full Kaggle pipeline → ingest mini
    python -m db.ingest --source kaggle --no-db      # build artifacts only, skip DB writes

Artifacts produced under data/artifacts/:
    main.parquet         — full training set with embeddings (~40k movies)
    mini.parquet         — top-200 popular movies; a subset of main (fast for dev/CI)
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
from db.ingestion.fetch import fetch_artifacts

log = logging.getLogger(__name__)

_NESTED_COLS = (
    "genres", "cast", "crew", "keywords",
    "production_companies", "production_countries", "spoken_languages",
    "belongs_to_collection", "top3_cast", "director",
)


def _save(df: pd.DataFrame, embeddings: np.ndarray, path: Path) -> None:
    """Persist *df* with an embedding column to a parquet file.

    Nested list/dict columns are JSON-encoded so pyarrow can serialise them
    reliably.
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


def run_from_artifact(name: str) -> None:
    """Ingest pre-built parquet artifact(s) without running the embedding pipeline.

    Args:
        name: Which artifact(s) to ingest — "main", "mini", or "all" (main + mini).

    Raises:
        FileNotFoundError: If the requested parquet file does not exist under
            data/artifacts/. Run with --source hf to download it.
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
                "Run `python -m db.ingest` (default: --source hf) to download pre-built artifacts,\n"
                "or `python -m db.ingest --source kaggle --no-db` to build them locally."
            )
        df, embeddings = _load_artifact(path)
        load.ingest(df, embeddings)


def run_full(args: argparse.Namespace) -> None:
    """Download from Kaggle, clean, split, embed all sets, save artifacts, optionally ingest."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    representation = settings.representation
    split_config = settings.split

    download.fetch(RAW_DATA_DIR, force=args.force_download)

    df = clean.prepare(RAW_DATA_DIR)
    main_df, mini_df, eval_df = split.three_way(
        df,
        mini_size=split_config.mini_size if args.mini_size is None else args.mini_size,
        eval_frac=split_config.eval_frac if args.eval_frac is None else args.eval_frac,
        seed=split_config.seed if args.seed is None else args.seed,
    )

    all_texts = list(main_df["composite_text"]) + list(eval_df["composite_text"])
    all_emb = embed.encode_all(
        all_texts,
        model_name=representation.model,
        expected_dim=representation.embedding_dim,
        batch_size=args.embed_batch_size,
    )

    n_main = len(main_df)
    main_emb = all_emb[:n_main]
    eval_emb = all_emb[n_main:]

    id_to_emb: dict[int, np.ndarray] = dict(zip(main_df["id"], main_emb))
    mini_emb = np.array([id_to_emb[mid] for mid in mini_df["id"]], dtype=np.float32)

    _save(main_df, main_emb, ARTIFACTS_DIR / "main.parquet")
    _save(mini_df, mini_emb, ARTIFACTS_DIR / "mini.parquet")
    _save(eval_df, eval_emb, ARTIFACTS_DIR / "eval_holdout.parquet")

    if not args.no_db:
        names = ["main", "mini"] if args.set == "all" else [args.set]
        dfs = {"main": main_df, "mini": mini_df}
        embs = {"main": main_emb, "mini": mini_emb}
        for n in names:
            load.ingest(dfs[n], embs[n])


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CinePal catalogue ingestion pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--source", choices=["hf", "local", "kaggle"], default="hf",
        help="Data source: 'hf' downloads pre-built artifacts from Hugging Face (default), "
             "'local' uses existing data/artifacts/, 'kaggle' runs the full build pipeline.",
    )
    p.add_argument(
        "--set", choices=["mini", "main", "all"], default="mini",
        dest="set",
        help="Which set(s) to write to the DB (default: mini). "
             "mini is a subset of main — ingesting main includes the same popular movies.",
    )
    p.add_argument(
        "--no-db", action="store_true",
        help="Skip all DB writes. Only meaningful with --source kaggle.",
    )
    p.add_argument(
        "--force-download", action="store_true",
        help="(kaggle only) Re-download raw data even if already present.",
    )
    p.add_argument(
        "--mini-size", type=int, default=None, metavar="N",
        help="(kaggle only) Number of movies in the mini set (default: config split.mini_size).",
    )
    p.add_argument(
        "--eval-frac", type=float, default=None, metavar="F",
        help="(kaggle only) Fraction of the dataset held out for evaluation (default: config split.eval_frac).",
    )
    p.add_argument(
        "--seed", type=int, default=None,
        help="(kaggle only) Random seed for reproducible splits (default: config split.seed).",
    )
    p.add_argument(
        "--embed-batch-size", type=int, default=256, metavar="B",
        help="(kaggle only) Sentence-transformer encoding batch size (default: 256).",
    )
    return p.parse_args()


def main() -> None:
    """CLI entry point."""
    configure_logging()
    args = _parse_args()

    if args.source == "hf":
        if args.no_db:
            log.warning("--no-db has no effect with --source hf (no DB writes happen after fetch)")
        fetch_artifacts()
        run_from_artifact(args.set)
    elif args.source == "local":
        if args.no_db:
            log.warning("--no-db has no effect with --source local")
        run_from_artifact(args.set)
    else:
        run_full(args)


if __name__ == "__main__":
    main()
