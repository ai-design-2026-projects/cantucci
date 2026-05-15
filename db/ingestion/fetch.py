"""Download pre-built parquet artifacts from a Hugging Face Dataset repo."""
import argparse
import logging
import os
from pathlib import Path

from huggingface_hub import snapshot_download

from backend.settings import ARTIFACTS_DIR, get_env

log = logging.getLogger(__name__)


def fetch_artifacts(
    repo_id: str | None = None,
    *,
    token: str | None = None,
    artifacts_dir: Path | None = None,
) -> Path:
    """Download parquet artifacts from a Hugging Face Dataset repo, returning the local path.
    Args:
        - repo_id: HF dataset repo id (e.g. "user/cinepal-embeddings"). Falls back to the CINEPAL_ARTIFACTS_REPO env var.
        - token: HF access token for private repos. Can be omitted for public repos. Falls back to HF_TOKEN env var. 
        - artifacts_dir: Local destination directory. Defaults to data/artifacts/.
    Returns:
        Path to the local artifacts directory.
    Raises:
        ValueError: If no repo id is provided and CINEPAL_ARTIFACTS_REPO is unset.
    """
    env = get_env()
    resolved_repo = repo_id or env.cinepal_artifacts_repo
    if not resolved_repo:
        raise ValueError(
            "HF repo id is required. Set CINEPAL_ARTIFACTS_REPO in .env "
            "or pass --repo explicitly."
        )
    resolved_token = token or os.environ.get("HF_TOKEN") or None
    dest = artifacts_dir or ARTIFACTS_DIR
    dest.mkdir(parents=True, exist_ok=True)

    log.info("downloading artifacts", extra={"repo": resolved_repo, "dest": str(dest)})
    snapshot_download(
        repo_id=resolved_repo,
        repo_type="dataset",
        local_dir=str(dest),
        allow_patterns=["*.parquet"],
        token=resolved_token,
    )
    log.info("artifacts ready", extra={"dest": str(dest)})
    return dest