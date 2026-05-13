"""Tests for backend/settings.py — config load, hash, snapshot, env override."""

import os

import pytest

from backend.settings import (
    get_config_hash,
    get_config_snapshot,
    get_settings,
    openai_api_key,
    database_url,
    _load_raw,
)


class TestGetSettings:
    def test_returns_settings_with_model_name(self):
        cfg = get_settings()
        assert isinstance(cfg.model.name, str) and cfg.model.name

    def test_model_seed_is_int(self):
        assert isinstance(get_settings().model.seed, int)

    def test_session_max_turns_positive(self):
        assert get_settings().session.max_turns > 0

    def test_session_convergence_turns_positive(self):
        assert get_settings().session.convergence_turns > 0

    def test_session_cost_limit_positive(self):
        assert get_settings().session.cost_limit_usd > 0.0

    def test_retrieval_top_k_positive(self):
        assert get_settings().retrieval.top_k > 0

    def test_clustering_min_cluster_size_positive(self):
        assert get_settings().clustering.min_cluster_size > 0

    def test_returns_equal_value_across_calls(self):
        assert get_settings() == get_settings()


class TestGetConfigHash:
    def test_returns_8_char_hex(self):
        h = get_config_hash()
        assert len(h) == 8
        int(h, 16)

    def test_stable_across_calls(self):
        assert get_config_hash() == get_config_hash()


class TestGetConfigSnapshot:
    def test_contains_model_key(self):
        snap = get_config_snapshot()
        assert "model" in snap

    def test_contains_session_key(self):
        assert "session" in get_config_snapshot()


class TestEnvOverride:
    def test_missing_database_url_raises(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(KeyError):
            database_url()

    def test_database_url_from_env(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://test")
        assert database_url() == "postgres://test"

    def test_missing_openai_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(KeyError):
            openai_api_key()

    def test_openai_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert openai_api_key() == "sk-test"


class TestLoadRawMissingFile:
    def test_raises_file_not_found(self, tmp_path):
        _load_raw.cache_clear()
        with pytest.raises(FileNotFoundError):
            _load_raw(str(tmp_path / "nonexistent.yaml"))
        _load_raw.cache_clear()
