"""Centralized configuration and path management for the CinePal backend.

Three concerns live here:
  1. **Filesystem paths** — module-level constants so callers never recompute
     ``Path(__file__).parents[N]``.
  2. **Environment settings** — typed ``EnvSettings`` (pydantic-settings) for secrets and
     runtime knobs. Use ``get_env()`` to access; fields map directly to env-var names.
  3. **Runtime config** — typed Pydantic models that mirror ``configs/default.yaml``.
     Use ``get_settings()`` to load and validate the active YAML config file.

Usage::
    from backend.settings import get_settings, get_config_hash, get_env, BACKEND_DIR, prompts_dir

    cfg = get_settings()
    model_name = cfg.models.strong.name
    seed = cfg.models.strong.seed
    prompt_path = prompts_dir("orchestrator") / "system_v1.j2"
    hf_repo = cfg.ingestion.hf_repo
    main_parquet = cfg.ingestion.artifacts.main

    db_url = get_env().database_url
    api_key = get_env().openai_api_key
"""
import functools
import hashlib
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
"""Repository root — one level above ``backend/``."""

BACKEND_DIR: Path = PROJECT_ROOT / "backend"
"""Absolute path to the ``backend/`` package directory."""

DATA_DIR: Path = PROJECT_ROOT / "data"
"""Directory that holds the raw CSVs and generated artifacts."""

ARTIFACTS_DIR: Path = DATA_DIR / "artifacts"
"""Directory containing parquet artifacts downloaded from the HF dataset repo."""

CONFIGS_DIR: Path = PROJECT_ROOT / "configs"
"""Directory that holds YAML condition configs (``default.yaml``, etc.)."""

DEFAULT_CONFIG_PATH: Path = CONFIGS_DIR / "default.yaml"
"""Default config file loaded by ``get_settings()`` unless overridden."""

MIGRATIONS_DIR: Path = PROJECT_ROOT / "db" / "migrations"
"""Directory containing numbered ``.sql`` migration files."""

LOGS_DIR: Path = PROJECT_ROOT / "logs"
"""Directory where per-run, per-component log files are written."""


class ModelConfig(BaseModel):
    """LLM model parameters.

    Attributes:
        name:       Model identifier string (e.g. ``"gpt-4o-mini"``).
        provider:   API provider — ``"openai"`` or ``"openrouter"``.
        seed:       RNG seed for reproducible completions.
        max_tokens: Maximum completion tokens per call.
        dry_run:    When True, every ``llm_harness.call()`` short-circuits to a
                    fixture response instead of hitting the real API. Used by
                    the smoke-test config; never enable in production.
    """
    name: str
    provider: str = "openai"
    seed: int
    max_tokens: int
    dry_run: bool = False


class ModelTiers(BaseModel):
    """Two-tier LLM configuration: a strong default and a cheaper fast tier.

    Judgment-heavy agents (decision routing, profile extraction, cluster
    refinement, convergence check) use ``strong``. Mechanical prompts
    (query reformulation, cluster naming) use ``fast``.

    Attributes:
        strong: Primary model used by every critical-path agent and recorded
                as the canonical session model on the ``runs`` / ``sessions`` rows.
        fast:   Smaller / cheaper model used for bounded, low-judgment prompts.
    """
    strong: ModelConfig
    fast: ModelConfig


class SessionConfig(BaseModel):
    """Per-session runtime limits.
    Attributes:
        max_turns:            Hard turn budget before the session is auto-closed.
        state_turns:          Kept for replay compatibility; no longer wired in the
                              state pipeline (LLM gate owns end-detection now).
        cost_limit_usd:       Maximum USD spend allowed for one session.
        max_recommendations:  Maximum number of show-type turns allowed before the
                              session is force-terminated. Checked by the hard-limit
                              gate before any LLM call.
    """
    max_turns: int
    state_turns: int
    cost_limit_usd: float
    max_recommendations: int


class RetrievalConfig(BaseModel):
    """Vector-search parameters.
    Attributes:
        top_k: Maximum number of candidate films to retrieve per turn.
        ivfflat_probes: Number of IVFFlat lists probed per vector_search query.
                        The index is built with lists = 100; values >= 100 give
                        exact search. Applied via SET LOCAL ivfflat.probes.
    """
    top_k: int
    ivfflat_probes: int


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


class UmapConfig(BaseModel):
    """UMAP dimensionality-reduction parameters applied before HDBSCAN.

    Attributes:
        enabled:      Skip reduction entirely when False (raw embeddings → HDBSCAN).
        n_components: Target dimensionality for HDBSCAN's density estimation.
        n_neighbors: UMAP neighbourhood size; clamped to ``pool_size - 1`` at runtime.
        min_dist:     Lower values preserve tighter local structure (use 0.0 for clustering).
        metric:       Distance metric used by UMAP (``"cosine"`` for unit-norm text embeddings).
    """

    enabled: bool = True
    n_components: int = 5
    n_neighbors: int = 15
    min_dist: float = 0.0
    metric: str = "cosine"


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
        umap:                    UMAP pre-reduction parameters (see ``UmapConfig``).
    """

    min_cluster_size: int
    min_samples: int
    cluster_selection_method: str
    assignment_threshold: float
    top_titles_per_cluster: int
    min_singleton_floor: int = 3
    umap: UmapConfig = UmapConfig()


class IngestionArtifacts(BaseModel):
    """Timestamped parquet paths in the HF dataset repo.

    Each value is a full ``path_in_repo`` (e.g. ``"embeddings/main_20260517.parquet"``)
    so the HF repo can be organised into directories — ``snapshots/`` holds the
    stage-1 cleaned catalogue produced by ``db/scrape.py``, ``embeddings/`` holds
    the three stage-2 parquets produced by the Colab notebook.

    Pinning specific filenames in YAML (rather than a constant name like
    ``main.parquet``) is what makes the catalogue version part of the
    ``config_hash`` — switching snapshots changes the hash, preserving the
    replayability contract when artifacts get refreshed.

    Attributes:
        snapshot:     Stage-1 cleaned catalogue parquet (no embeddings), e.g.
                      ``"snapshots/snapshot_20260517.parquet"``. Consumed by the
                      Colab embedding notebook; never ingested into the DB directly.
        main:         Stage-2 full production parquet with embeddings, e.g.
                      ``"embeddings/main_20260517.parquet"``.
        mini:         Stage-2 dev/CI subset parquet with embeddings.
        eval_holdout: Stage-2 disjoint evaluation parquet (downloaded but never ingested).
    """

    snapshot: str
    main: str
    mini: str
    eval_holdout: str


class IngestionConfig(BaseModel):
    """Hugging Face artifact source for catalogue ingestion.

    Attributes:
        hf_repo:   HF dataset repo id, e.g. ``"446f6e6e79/CinePal-embeddings"``.
        artifacts: Per-split filenames inside the repo.
    """

    hf_repo: str
    artifacts: IngestionArtifacts


class EvalModelConfig(BaseModel):
    """LLM model parameters for an eval component (oracle or judge).

    Attributes:
        name:       Model identifier string.
        provider:   API provider — ``"openai"`` or ``"openrouter"``.
        seed:       RNG seed for reproducible completions.
        max_tokens: Maximum completion tokens per call.
    """

    name: str
    provider: str = "openrouter"
    seed: int
    max_tokens: int


class EvalOracleConfig(BaseModel):
    """Oracle-agent parameters for automated eval sessions.

    Attributes:
        model:           LLM model to drive the Oracle.
        cost_limit_usd:  Total USD ceiling for Oracle spend in one eval run.
    """

    model: EvalModelConfig
    cost_limit_usd: float


class EvalJudgeConfig(BaseModel):
    """LLM-judge parameters for post-session scoring.

    Attributes:
        model:          LLM model to drive the judge.
        cost_limit_usd: Total USD ceiling for judge spend in one eval run.
    """

    model: EvalModelConfig
    cost_limit_usd: float


class EvalMetricsConfig(BaseModel):
    """Objective metric parameters.

    Attributes:
        k: Rank cutoff for precision@K, recall@K, and NDCG@K.
    """

    k: int = 5


class EvalConfig(BaseModel):
    """Top-level eval configuration block.

    Attributes:
        oracle:  Oracle-agent model and budget.
        judge:   LLM-judge model and budget.
        metrics: Objective metric parameters.
    """

    oracle: EvalOracleConfig
    judge: EvalJudgeConfig
    metrics: EvalMetricsConfig = EvalMetricsConfig()


class Settings(BaseModel):
    """Full typed configuration loaded from a YAML config file.

    Attributes:
        models:         Two-tier LLM model parameters (``strong`` + ``fast``).
        session:        Session runtime limits.
        retrieval:      Vector-search parameters.
        split:          Dataset-generation split parameters.
        representation: Embedding model configuration.
        clustering:     HDBSCAN parameters.
        ingestion:      HF artifact source (repo + per-split filenames).
        eval:           Eval pipeline parameters (oracle, judge, metrics).
    """

    models: ModelTiers
    session: SessionConfig
    retrieval: RetrievalConfig
    split: SplitConfig
    representation: RepresentationConfig
    clustering: ClusteringConfig
    ingestion: IngestionConfig
    eval: EvalConfig | None = None

class EnvSettings(BaseSettings):
    """Typed environment settings loaded from the environment and ``.env`` file.

    Each field maps directly to an environment variable of the same name
    (upper-cased automatically by pydantic-settings).  Missing required fields
    raise ``pydantic.ValidationError`` at instantiation time.

    Attributes:
        database_url:    Postgres connection string. Optional so artifact-only
                         paths (e.g. the Colab TMDB snapshot) can instantiate
                         ``EnvSettings`` without a DB; the connection pool in
                         ``backend/api/db.py`` raises if it's empty when used.
        openai_api_key:  OpenAI API key for LLM calls.
        hf_token:        Hugging Face API token (for private repos).
        tmdb_api_key:    TMDB API key — only used by the local scrape entrypoint
                         (``db/scrape.py``).
        log_level:       Root logging level (default ``INFO``).
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        extra="ignore",
    )

    database_url: str = ""
    auth_secret: str
    jwt_ttl_seconds: int = 7 * 24 * 3600
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    hf_token: str = ""
    tmdb_api_key: str = ""
    log_level: str = "INFO"


def get_env() -> EnvSettings:
    """Return a fresh ``EnvSettings`` instance reflecting the current environment.

    Reads env vars and the ``.env`` file on every call so that monkeypatching
    in tests is reflected immediately.

    Returns:
        A validated ``EnvSettings`` instance.

    Raises:
        pydantic.ValidationError: If a required env var (e.g. ``DATABASE_URL``) is unset.
    """
    return EnvSettings()


def prompts_dir(agent: str) -> Path:
    """Return the prompts directory for the named agent module.

    Args:
        agent: Agent module name as it appears under ``backend/``,
               e.g. ``"orchestrator"``, ``"cluster"``, ``"ambiguity"``.

    Returns:
        ``Path`` to ``backend/<agent>/prompts/``.
    """
    return BACKEND_DIR / agent / "prompts"


def eval_prompts_dir(component: str) -> Path:
    """Return the prompts directory for an eval component.

    Args:
        component: Eval sub-package name — ``"oracle"`` or ``"judge"``.

    Returns:
        ``Path`` to ``eval/<component>/prompts/`` under the project root.
    """
    return PROJECT_ROOT / "eval" / component / "prompts"



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
