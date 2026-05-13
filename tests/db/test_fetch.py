"""Unit tests for db.ingestion.fetch — monkeypatches HF so no network calls are made."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db.ingestion.fetch import fetch_artifacts


def test_fetch_artifacts_calls_snapshot_download(tmp_path: Path) -> None:
    """fetch_artifacts should forward the right arguments to snapshot_download."""
    with patch("db.ingestion.fetch.snapshot_download") as mock_dl:
        fetch_artifacts(
            repo_id="user/cinepal-embeddings",
            token="hf_test",
            artifacts_dir=tmp_path,
        )
        mock_dl.assert_called_once_with(
            repo_id="user/cinepal-embeddings",
            repo_type="dataset",
            local_dir=str(tmp_path),
            allow_patterns=["*.parquet"],
            token="hf_test",
        )


def test_fetch_artifacts_reads_env_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_artifacts should fall back to env vars when called without explicit args."""
    monkeypatch.setenv("CINEPAL_ARTIFACTS_REPO", "org/my-repo")
    monkeypatch.setenv("HF_TOKEN", "hf_env_token")

    with patch("db.ingestion.fetch.snapshot_download") as mock_dl:
        fetch_artifacts(artifacts_dir=tmp_path)
        mock_dl.assert_called_once()
        call_kwargs = mock_dl.call_args.kwargs
        assert call_kwargs["repo_id"] == "org/my-repo"
        assert call_kwargs["token"] == "hf_env_token"


def test_fetch_artifacts_raises_without_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fetch_artifacts should raise ValueError when no repo id is configured."""
    monkeypatch.delenv("CINEPAL_ARTIFACTS_REPO", raising=False)

    with pytest.raises(ValueError, match="CINEPAL_ARTIFACTS_REPO"):
        fetch_artifacts(artifacts_dir=tmp_path)


def test_fetch_artifacts_token_optional_for_public_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_artifacts should pass token=None when no token is provided (public repos)."""
    monkeypatch.delenv("HF_TOKEN", raising=False)

    with patch("db.ingestion.fetch.snapshot_download") as mock_dl:
        fetch_artifacts(repo_id="org/public-repo", artifacts_dir=tmp_path)
        call_kwargs = mock_dl.call_args.kwargs
        assert call_kwargs["token"] is None


def test_fetch_artifacts_creates_dest_dir(tmp_path: Path) -> None:
    """fetch_artifacts should create the destination directory if it does not exist."""
    dest = tmp_path / "nested" / "artifacts"
    assert not dest.exists()

    with patch("db.ingestion.fetch.snapshot_download"):
        fetch_artifacts(repo_id="org/repo", artifacts_dir=dest)

    assert dest.exists()
