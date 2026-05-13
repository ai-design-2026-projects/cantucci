"""Tests for backend/settings.py — config load, hash, snapshot, env override."""

import pytest
from pydantic import ValidationError

from backend.settings import (
    get_config_hash,
    get_config_snapshot,
    get_env,
    get_settings,
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

    def test_split_parameters_positive(self):
        cfg = get_settings().split
        assert cfg.mini_size > 0
        assert 0.0 < cfg.eval_frac < 1.0
        assert isinstance(cfg.seed, int)

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
        # Use _env_file=None to bypass .env so only os.environ is consulted.
        from backend.settings import EnvSettings
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with pytest.raises(ValidationError):
            EnvSettings(_env_file=None)

    def test_database_url_from_env(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert get_env().database_url == "postgres://test"

    def test_missing_openai_key_raises(self, monkeypatch):
        # Use _env_file=None to bypass .env so only os.environ is consulted.
        from backend.settings import EnvSettings
        monkeypatch.setenv("DATABASE_URL", "postgres://test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValidationError):
            EnvSettings(_env_file=None)

    def test_openai_key_from_env(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert get_env().openai_api_key == "sk-test"


class TestLoadRawMissingFile:
    def test_raises_file_not_found(self, tmp_path):
        _load_raw.cache_clear()
        with pytest.raises(FileNotFoundError):
            _load_raw(str(tmp_path / "nonexistent.yaml"))
        _load_raw.cache_clear()
