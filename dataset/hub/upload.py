import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from huggingface_hub import HfApi

from backend.settings import get_env

log = logging.getLogger(__name__)

_NESTED_COLS = (
    "genres", "cast", "crew", "keywords",
    "production_companies", "production_countries", "spoken_languages",
    "belongs_to_collection", "top3_cast", "director",
)


class _NumpyJSONEncoder(json.JSONEncoder):
    """JSON encoder that understands the numpy types parquet round-trips into.

    Reading a snapshot parquet (e.g. in the Colab notebook) deserialises
    list-typed columns as ``np.ndarray`` and integer/float scalars inside
    them as ``np.generic``. Stock ``json.dumps`` raises ``TypeError`` on
    both. Convert to native Python here rather than mutating ``out`` row by
    row.
    """

    def default(self, o: Any) -> Any:
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, np.generic):
            return o.item()
        return super().default(o)


def _save_parquet(
    df: pd.DataFrame,
    text_emb: np.ndarray,
    path: Path,
    *,
    review_emb: np.ndarray | None = None,
    trailer_emb: np.ndarray | None = None,
) -> None:
    """Persist *df* + per-row embeddings to a parquet file.

    Nested list/dict columns are JSON-encoded so pyarrow serialises them
    losslessly; ``db.ingest._load_artifact`` reverses the encoding on load.

    Args:
        df:          Cleaned DataFrame.
        text_emb:    Float32 array of shape (n, dim) — text embedding for every row.
        path:        Output parquet path.
        review_emb:  Optional float32 array of shape (n, dim) — review embeddings;
                     rows without reviews should be all-zero. Omitted if None.
        trailer_emb: Optional float32 array of shape (n, dim) — CLIP trailer
                     embeddings projected to match the text embedding dimension.
                     Rows without trailers should be all-zero. Omitted if None.
    """
    if len(df) != len(text_emb):
        raise ValueError(f"df has {len(df)} rows but text_emb has {len(text_emb)} rows")
    out = df.copy()
    out["text_embedding"] = [arr.tolist() for arr in text_emb]
    if review_emb is not None:
        if len(df) != len(review_emb):
            raise ValueError(f"df has {len(df)} rows but review_emb has {len(review_emb)} rows")
        out["review_embedding"] = [arr.tolist() for arr in review_emb]
    if trailer_emb is not None:
        if len(df) != len(trailer_emb):
            raise ValueError(f"df has {len(df)} rows but trailer_emb has {len(trailer_emb)} rows")
        out["trailer_embedding"] = [arr.tolist() for arr in trailer_emb]
    for col in _NESTED_COLS:
        if col in out.columns:
            out[col] = out[col].apply(lambda v: json.dumps(v, cls=_NumpyJSONEncoder))
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
    main_review_emb: np.ndarray | None = None,
    mini_review_emb: np.ndarray | None = None,
    eval_review_emb: np.ndarray | None = None,
    main_trailer_emb: np.ndarray | None = None,
    mini_trailer_emb: np.ndarray | None = None,
    eval_trailer_emb: np.ndarray | None = None,
    repo_id: str,
    artifacts_dir: Path,
    timestamp: str | None = None,
    token: str | None = None,
    commit_message: str | None = None,
) -> dict[str, str]:
    """Write the three parquets locally and upload each to the HF dataset repo.

    Args:
        main_df / mini_df / eval_df:       Cleaned DataFrames from ``split.three_way``.
        main_emb / mini_emb / eval_emb:    Aligned text embedding arrays (float32).
        main_review_emb / mini_review_emb / eval_review_emb:
                                           Optional aligned review embedding arrays (float32).
                                           Rows without reviews should be all-zero.
        main_trailer_emb / mini_trailer_emb / eval_trailer_emb:
                                           Optional aligned CLIP trailer embedding arrays
                                           (float32, projected to match text embedding dim).
                                           Rows without trailers should be all-zero.
        repo_id:        Target HF dataset repo, e.g. ``"446f6e6e79/CinePal-embeddings"``.
        artifacts_dir:  Local directory to write the parquets to before upload.
        timestamp:      Suffix appended to each filename. Defaults to today's UTC date
                        (``YYYYMMDD``). Pass a custom value to override (e.g. for tests).
        token:          HF token. Falls back to ``get_env().hf_token`` (sourced from ``HF_TOKEN``).
        commit_message: Commit message for the HF upload. Defaults to a description
                        that includes the timestamp.

    Returns:
        Dict mapping split name → uploaded filename. Print this in the Colab
        notebook so the values can be pasted into ``configs/default.yaml``.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d")
    resolved_token = token or get_env().hf_token or None

    # Local on-disk names stay flat (we write next to other artifacts);
    # only the HF path-in-repo carries the embeddings/ prefix.
    local_names: dict[str, str] = {
        "main": f"main_{stamp}.parquet",
        "mini": f"mini_{stamp}.parquet",
        "eval_holdout": f"eval_holdout_{stamp}.parquet",
    }
    repo_paths: dict[str, str] = {
        split: f"embeddings/{name}" for split, name in local_names.items()
    }

    _save_parquet(main_df, main_emb, artifacts_dir / local_names["main"],
                  review_emb=main_review_emb, trailer_emb=main_trailer_emb)
    _save_parquet(mini_df, mini_emb, artifacts_dir / local_names["mini"],
                  review_emb=mini_review_emb, trailer_emb=mini_trailer_emb)
    _save_parquet(eval_df, eval_emb, artifacts_dir / local_names["eval_holdout"],
                  review_emb=eval_review_emb, trailer_emb=eval_trailer_emb)

    api = HfApi()
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True, token=resolved_token)
    msg = commit_message or f"snapshot {stamp}"
    for split, path_in_repo in repo_paths.items():
        log.info(
            "uploading artifact",
            extra={"split": split, "path_in_repo": path_in_repo, "repo": repo_id},
        )
        api.upload_file(
            path_or_fileobj=str(artifacts_dir / local_names[split]),
            path_in_repo=path_in_repo,
            repo_id=repo_id,
            repo_type="dataset",
            token=resolved_token,
            commit_message=msg,
        )

    log.info("upload complete", extra={"repo": repo_id, "files": repo_paths})
    return repo_paths


def upload_snapshot(
    parquet_path: Path,
    *,
    repo_id: str,
    token: str | None = None,
    timestamp: str | None = None,
    commit_message: str | None = None,
) -> str:
    """Upload a stage-1 cleaned snapshot parquet to ``<repo_id>/snapshots/``.
    Args:
        parquet_path:   Local path to the cleaned snapshot parquet produced by
                        ``db/scrape.py``.
        repo_id:        Target HF dataset repo, e.g. ``"446f6e6e79/CinePal-embeddings"``.
        token:          HF token. Falls back to ``get_env().hf_token`` (sourced from ``HF_TOKEN``).
        timestamp:      Filename suffix (``YYYYMMDD``). Defaults to today's UTC date.
        commit_message: Commit message for the HF upload. Defaults to a description
                        that includes the timestamp.
    Returns:
        The ``path_in_repo`` of the uploaded file, e.g.
        ``"snapshots/snapshot_20260517.parquet"``. Print this so it can be pinned
        in ``configs/default.yaml`` under ``ingestion.artifacts.snapshot``.
    """
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d")
    resolved_token = token or get_env().hf_token or None
    path_in_repo = f"snapshots/snapshot_{stamp}.parquet"

    api = HfApi()
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True, token=resolved_token)
    log.info(
        "uploading snapshot",
        extra={"path_in_repo": path_in_repo, "repo": repo_id, "src": str(parquet_path)},
    )
    api.upload_file(
        path_or_fileobj=str(parquet_path),
        path_in_repo=path_in_repo,
        repo_id=repo_id,
        repo_type="dataset",
        token=resolved_token,
        commit_message=commit_message or f"snapshot {stamp}",
    )
    log.info("snapshot upload complete", extra={"repo": repo_id, "path_in_repo": path_in_repo})
    return path_in_repo
