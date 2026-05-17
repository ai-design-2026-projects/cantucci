"""Upload timestamped parquet artifacts to the HuggingFace dataset repo.

Only invoked from ``notebooks/embed_in_colab.ipynb`` after the catalogue has
been snapshotted, split, and embedded. This is the **only** code path in the
repo that writes to HuggingFace.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from huggingface_hub import HfApi

log = logging.getLogger(__name__)

_NESTED_COLS = (
    "genres", "cast", "crew", "keywords",
    "production_companies", "production_countries", "spoken_languages",
    "belongs_to_collection", "top3_cast", "director",
)


def _save_parquet(df: pd.DataFrame, embeddings: np.ndarray, path: Path) -> None:
    """Persist *df* + per-row embeddings to a parquet file.

    Nested list/dict columns are JSON-encoded so pyarrow serialises them
    losslessly; ``db.ingest._load_artifact`` reverses the encoding on load.
    """
    if len(df) != len(embeddings):
        raise ValueError(f"df has {len(df)} rows but embeddings has {len(embeddings)} rows")
    out = df.copy()
    out["embedding"] = [arr.tolist() for arr in embeddings]
    for col in _NESTED_COLS:
        if col in out.columns:
            out[col] = out[col].apply(json.dumps)
    out.to_parquet(path, index=False)
    log.info("artifact saved", extra={"path": str(path), "rows": len(out)})


def upload_artifacts(
    main_df: pd.DataFrame,
    mini_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    main_emb: np.ndarray,
    mini_emb: np.ndarray,
    eval_emb: np.ndarray,
    *,
    repo_id: str,
    artifacts_dir: Path,
    timestamp: str | None = None,
    token: str | None = None,
    commit_message: str | None = None,
) -> dict[str, str]:
    """Write the three parquets locally and upload each to the HF dataset repo.

    Args:
        main_df / mini_df / eval_df:  Cleaned DataFrames from ``split.three_way``.
        main_emb / mini_emb / eval_emb:  Aligned embedding arrays (float32).
        repo_id:        Target HF dataset repo, e.g. ``"446f6e6e79/CinePal-embeddings"``.
        artifacts_dir:  Local directory to write the parquets to before upload.
        timestamp:      Suffix appended to each filename. Defaults to today's UTC date
                        (``YYYYMMDD``). Pass a custom value to override (e.g. for tests).
        token:          HF token. Falls back to the ``HF_TOKEN`` env var.
        commit_message: Commit message for the HF upload. Defaults to a description
                        that includes the timestamp.

    Returns:
        Dict mapping split name → uploaded filename. Print this in the Colab
        notebook so the values can be pasted into ``configs/default.yaml``.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d")
    resolved_token = token or os.environ.get("HF_TOKEN") or None

    files: dict[str, str] = {
        "main": f"main_{stamp}.parquet",
        "mini": f"mini_{stamp}.parquet",
        "eval_holdout": f"eval_holdout_{stamp}.parquet",
    }

    _save_parquet(main_df, main_emb, artifacts_dir / files["main"])
    _save_parquet(mini_df, mini_emb, artifacts_dir / files["mini"])
    _save_parquet(eval_df, eval_emb, artifacts_dir / files["eval_holdout"])

    api = HfApi()
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True, token=resolved_token)
    msg = commit_message or f"snapshot {stamp}"
    for split, filename in files.items():
        log.info("uploading artifact", extra={"split": split, "filename": filename, "repo": repo_id})
        api.upload_file(
            path_or_fileobj=str(artifacts_dir / filename),
            path_in_repo=filename,
            repo_id=repo_id,
            repo_type="dataset",
            token=resolved_token,
            commit_message=msg,
        )

    log.info("upload complete", extra={"repo": repo_id, "files": files})
    return files
