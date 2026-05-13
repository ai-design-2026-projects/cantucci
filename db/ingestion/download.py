"""Kaggle dataset download — rounakbanik/the-movies-dataset."""
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_DATASET = "rounakbanik/the-movies-dataset"
_SENTINEL = "movies_metadata.csv"


def fetch(data_dir: Path, *, force: bool = False) -> Path:
    """
    Download the Kaggle dataset to *data_dir* and return the directory.

    Skips the download if movies_metadata.csv is already present (unless force=True).
    Raises RuntimeError if Kaggle credentials are missing or authentication fails.
    Args:
        - data_dir: Destination directory for the extracted CSVs.
        - force: Re-download even if data already exists.
    Returns:
        data_dir (for chaining).
    """
    # Check for existing data to avoid unnecessary downloads, since the Kaggle API doesn't support file-level checks.
    data_dir.mkdir(parents=True, exist_ok=True)
    if (data_dir / _SENTINEL).exists() and not force:
        log.info("raw data present, skipping download", extra={"path": str(data_dir)})
        return data_dir

    # Import kaggle API client. Raise a clear error if it's not installed or if authentication fails, since these are common issues.
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as exc:
        raise RuntimeError(
            "kaggle package not installed — run: pip install 'kaggle>=1.6'"
        ) from exc

    # Authenticate with Kaggle using the API client. Raise a clear error if authentication fails, which is often due to missing or misconfigured credentials.
    api = KaggleApi()
    try:
        api.authenticate()
    except Exception as exc:
        raise RuntimeError(
            "Kaggle authentication failed. Place credentials at ~/.kaggle/kaggle.json "
            "or set KAGGLE_USERNAME and KAGGLE_KEY environment variables."
        ) from exc

    # Download and unzip the dataset
    log.info("downloading", extra={"dataset": _DATASET, "dest": str(data_dir)})
    api.dataset_download_files(_DATASET, path=str(data_dir), unzip=True, quiet=False)
    log.info("download complete")
    return data_dir
