import logging
from pathlib import Path
from huggingface_hub import hf_hub_download

from backend.settings import ARTIFACTS_DIR, get_env

log = logging.getLogger(__name__)


def fetch_artifact(
    repo_id: str,
    filename: str,
    *,
    token: str | None = None,
    artifacts_dir: Path | None = None,
) -> Path:
    """
    Download a single parquet file from a HF Dataset repo and return its local path.
    Args:
        repo_id:        HF dataset repo id, e.g. ``"446f6e6e79/CinePal-embeddings"``.
        filename:       Exact filename inside the repo, e.g. ``"main_20260517.parquet"``.
                        Pinning the timestamped name here is what ties this run to a
                        specific snapshot for the replayability contract.
        token:          HF access token for private repos. Falls back to
                        ``get_env().hf_token`` (sourced from ``HF_TOKEN``).
        artifacts_dir:  Local destination directory. Defaults to ``data/artifacts/``.
    Returns:
        Absolute path to the downloaded parquet file on disk.
    """
    resolved_token = token or get_env().hf_token or None
    dest = artifacts_dir or ARTIFACTS_DIR
    dest.mkdir(parents=True, exist_ok=True)

    log.info(
        "downloading artifact",
        extra={"repo": repo_id, "file_name": filename, "dest": str(dest)},
    )
    local_path = hf_hub_download(
        repo_id=repo_id,
        repo_type="dataset",
        filename=filename,
        local_dir=str(dest),
        token=resolved_token,
    )
    log.info("artifact ready", extra={"path": local_path})
    return Path(local_path)
