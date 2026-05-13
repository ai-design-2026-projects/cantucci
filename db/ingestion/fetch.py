"""Download pre-built parquet artifacts from a Hugging Face Dataset repo."""
import argparse
import logging
import os
from pathlib import Path

from huggingface_hub import snapshot_download

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_ARTIFACTS_DIR = _ROOT / "data" / "artifacts"


def fetch_artifacts(
    repo_id: str | None = None,
    *,
    token: str | None = None,
    artifacts_dir: Path | None = None,
) -> Path:
    """Download *.parquet artifacts from a Hugging Face Dataset repo.

    Args:
        repo_id: HF dataset repo id (e.g. "user/cinepal-embeddings"). Falls back
            to the CINEPAL_ARTIFACTS_REPO env var.
        token: HF access token for private repos. Falls back to HF_TOKEN env var.
            Can be omitted for public repos.
        artifacts_dir: Local destination directory. Defaults to data/artifacts/.

    Returns:
        Path to the local artifacts directory.

    Raises:
        ValueError: If no repo id is provided and CINEPAL_ARTIFACTS_REPO is unset.
    """
    resolved_repo = repo_id or os.environ.get("CINEPAL_ARTIFACTS_REPO", "")
    if not resolved_repo:
        raise ValueError(
            "HF repo id is required. Set CINEPAL_ARTIFACTS_REPO in .env "
            "or pass --repo explicitly."
        )
    resolved_token = token or os.environ.get("HF_TOKEN") or None
    dest = artifacts_dir or _ARTIFACTS_DIR
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


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Download pre-built parquet artifacts from Hugging Face Datasets."
    )
    p.add_argument("--repo", metavar="REPO_ID",
                   help="HF dataset repo id, e.g. 'user/cinepal-embeddings' "
                        "(default: $CINEPAL_ARTIFACTS_REPO).")
    p.add_argument("--token", metavar="TOKEN",
                   help="HF access token for private repos (default: $HF_TOKEN).")
    p.add_argument("--dest", type=Path, metavar="DIR",
                   help="Local destination directory (default: data/artifacts/).")
    return p.parse_args()


if __name__ == "__main__":
    from backend.logging_setup import configure_logging
    configure_logging()
    args = _parse_args()
    fetch_artifacts(repo_id=args.repo, token=args.token, artifacts_dir=args.dest)
