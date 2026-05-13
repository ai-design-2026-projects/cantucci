"""Centralized configuration and path management for the CinePal backend.

Two concerns live here:
  1. **Filesystem paths** — module-level constants so callers never recompute
     ``Path(__file__).parents[N]``.
  2. **Runtime config** — typed Pydantic models that mirror ``configs/default.yaml``.
     Secrets (API keys, DB URL) come from the environment via ``.env``.

Usage::
    from backend.settings import get_settings, get_config_hash, BACKEND_DIR, prompts_dir

    cfg = get_settings()
    model_name = cfg.model.name
    seed = cfg.model.seed
    prompt_path = prompts_dir("orchestrator") / "system_v1.j2"
"""
import functools
import hashlib
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
"""Repository root — one level above ``backend/``."""

BACKEND_DIR: Path = PROJECT_ROOT / "backend"
"""Absolute path to the ``backend/`` package directory."""

DATA_DIR: Path = PROJECT_ROOT / "data"
"""Directory that holds the raw CSVs and generated artifacts."""

RAW_DATA_DIR: Path = DATA_DIR / "raw"
"""Directory containing the Kaggle source CSVs."""

ARTIFACTS_DIR: Path = DATA_DIR / "artifacts"
"""Directory containing generated parquet artifacts."""

CONFIGS_DIR: Path = PROJECT_ROOT / "configs"
"""Directory that holds YAML condition configs (``default.yaml``, etc.)."""

DEFAULT_CONFIG_PATH: Path = CONFIGS_DIR / "default.yaml"
"""Default config file loaded by ``get_settings()`` unless overridden."""

MIGRATIONS_DIR: Path = PROJECT_ROOT / "db" / "migrations"
"""Directory containing numbered ``.sql`` migration files."""


class ModelConfig(BaseModel):
    """LLM model parameters.

    Attributes:
        name:       Model identifier string (e.g. ``"gpt-4o-mini"``).
        seed:       RNG seed for reproducible completions.
        max_tokens: Maximum completion tokens per call.
    """
    name: str
    seed: int
    max_tokens: int


class SessionConfig(BaseModel):
    """Per-session runtime limits.
    Attributes:
        max_turns:         Hard turn budget before the session is auto-closed.
        convergence_turns: Number of consecutive show-type turns without
                           oracle rejection required to declare convergence.
        cost_limit_usd:    Maximum USD spend allowed for one session.
    """
    max_turns: int
    convergence_turns: int
    cost_limit_usd: float


class RetrievalConfig(BaseModel):
    """Vector-search parameters.
    Attributes:
        top_k: Maximum number of candidate films to retrieve per turn.
    """
    top_k: int


class SplitConfig(BaseModel):
    """Dataset-generation split parameters.

    Attributes:
        mini_size: Number of rows kept in the mini subset.
        eval_frac: Fraction of the dataset reserved for evaluation holdout.
        seed: Random seed for the split.
    """

    mini_size: int
    eval_frac: float
    seed: int


class RepresentationConfig(BaseModel):
    """Embedding model configuration.
    Attributes:
        model:          Sentence-transformer model identifier.
        embedding_dim:  Embedding vector dimensionality.
    """
    model: str
    embedding_dim: int


class ClusteringConfig(BaseModel):
    """HDBSCAN soft-clustering parameters.
    Attributes:
        min_cluster_size:        Minimum points to form a cluster.
        min_samples:             HDBSCAN ``min_samples`` (controls noise).
        cluster_selection_method: ``"eom"`` or ``"leaf"``.
        assignment_threshold:    Minimum soft-assignment score to include a film.
        top_titles_per_cluster:  How many top-scoring films to pass to the describer.
        min_singleton_floor:     Minimum candidate count to consider a fallback cluster
                                  (unused — kept for config compatibility).
    """

    min_cluster_size: int
    min_samples: int
    cluster_selection_method: str
    assignment_threshold: float
    top_titles_per_cluster: int
    min_singleton_floor: int = 3


class AmbiguityConfig(BaseModel):
    """Ambiguity agent parameters.
    Attributes:
        max_cluster_context: Maximum number of top clusters to consider when
                            generating a clarifying question.
    """

    max_cluster_context: int


class Settings(BaseModel):
    """Full typed configuration loaded from a YAML config file.

    Attributes:
        model:          LLM model parameters.
        session:        Session runtime limits.
        retrieval:      Vector-search parameters.
        split:          Dataset-generation split parameters.
        representation: Embedding model configuration.
        clustering:     HDBSCAN parameters.
        ambiguity:      Ambiguity agent parameters.
    """

    model: ModelConfig
    session: SessionConfig
    retrieval: RetrievalConfig
    split: SplitConfig
    representation: RepresentationConfig
    clustering: ClusteringConfig
    ambiguity: AmbiguityConfig

def prompts_dir(agent: str) -> Path:
    """Return the prompts directory for the named agent module.

    Args:
        agent: Agent module name as it appears under ``backend/``,
               e.g. ``"orchestrator"``, ``"cluster"``, ``"ambiguity"``.

    Returns:
        ``Path`` to ``backend/<agent>/prompts/``.
    """
    return BACKEND_DIR / agent / "prompts"


def database_url() -> str:
    """Return the Postgres connection string from the environment.

    Raises:
        KeyError: If ``DATABASE_URL`` is not set.
    """
    return os.environ["DATABASE_URL"]

def kaggle_username() -> str:
    """Return the Kaggle API username from the environment.

    Raises:
        KeyError: If ``KAGGLE_USERNAME`` is not set.
    """
    return os.environ["KAGGLE_USERNAME"]


def kaggle_key() -> str:
    """Return the Kaggle API key from the environment.

    Raises:
        KeyError: If ``KAGGLE_KEY`` is not set.
    """
    return os.environ["KAGGLE_KEY"]


def cinepal_artifacts_repo() -> str:
    """Return the Hugging Face repo id for pre-built parquet artifacts.

    Raises:
        KeyError: If ``CINEPAL_ARTIFACTS_REPO`` is not set.
    """
    return os.environ["CINEPAL_ARTIFACTS_REPO"]


def hf_token() -> str:
    """Return the Hugging Face API token from the environment.

    Raises:
        KeyError: If ``HF_TOKEN`` is not set.
    """
    return os.environ["HF_TOKEN"]


def openai_api_key() -> str:
    """Return the OpenAI API key from the environment.

    Raises:
        KeyError: If ``OPENAI_API_KEY`` is not set.
    """
    return os.environ["OPENAI_API_KEY"]


def log_level() -> str:
    """Return the log level string from the environment (default ``INFO``)."""
    return os.environ.get("LOG_LEVEL", "INFO").upper()


@functools.cache
def _load_raw(config_path: str) -> tuple[dict[str, Any], str]:
    """Load and hash a YAML config file. Cached by path string.

    Args:
        config_path: Absolute path string to the YAML file.

    Returns:
        Tuple of (parsed dict, SHA-256 8-char hex prefix).

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError:    If the file contains invalid YAML.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()[:8]
    data: dict[str, Any] = yaml.safe_load(raw_bytes)
    return data, digest


def get_settings() -> Settings:
    """Return the typed Settings object for the active config.

    Reads ``CONFIG_PATH`` env var; falls back to ``DEFAULT_CONFIG_PATH``.
    The result is cached after the first load.

    Returns:
        Fully-validated ``Settings`` instance.
    """
    path = os.environ.get("CONFIG_PATH", str(DEFAULT_CONFIG_PATH))
    data, _ = _load_raw(path)
    representation = data.get("representation", {})
    if isinstance(representation, dict):
        if "model" not in representation and "strategy" in representation:
            representation["model"] = representation.pop("strategy")
        if "embedding_dim" not in representation and "dim" in representation:
            representation["embedding_dim"] = representation.pop("dim")
    return Settings(**data)


def get_config_hash() -> str:
    """Return the 8-character SHA-256 prefix of the active config file.

    Used when creating run rows in the DB so sessions are replayable.

    Returns:
        8-char hex string.
    """
    path = os.environ.get("CONFIG_PATH", str(DEFAULT_CONFIG_PATH))
    _, digest = _load_raw(path)
    return digest


def get_config_snapshot() -> dict[str, Any]:
    """Return the raw config dict for storage in ``runs.config_snapshot``.

    Returns:
        Parsed YAML dict.
    """
    path = os.environ.get("CONFIG_PATH", str(DEFAULT_CONFIG_PATH))
    data, _ = _load_raw(path)
    return data
