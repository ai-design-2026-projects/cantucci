import functools
import hashlib
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
BACKEND_DIR: Path = PROJECT_ROOT / "backend"
DATA_DIR: Path = PROJECT_ROOT / "data"
ARTIFACTS_DIR: Path = DATA_DIR / "artifacts"
CONFIGS_DIR: Path = PROJECT_ROOT / "configs"
DEFAULT_CONFIG_PATH: Path = CONFIGS_DIR / "default.yaml"
MIGRATIONS_DIR: Path = PROJECT_ROOT / "db" / "migrations"
LOGS_DIR: Path = PROJECT_ROOT / "logs"


class ModelConfig(BaseModel):
    """LLM model parameters.

    Attributes:
        name:       Model identifier string (e.g. ``"gpt-4o-mini"``).
        provider:   API provider — ``"openai"`` or ``"openrouter"``.
        seed:       RNG seed for reproducible completions.
        max_tokens: Maximum completion tokens per call.
        dry_run:    When True, every ``llm_harness.call()`` short-circuits to a
                    fixture response instead of hitting the real API.
    """
    name: str
    provider: str = "openai"
    seed: int
    max_tokens: int
    dry_run: bool = False


class ModelTiers(BaseModel):
    """Two-tier LLM configuration: a strong default and a cheaper fast tier.

    Attributes:
        strong: Primary model for judgment-heavy agents.
        fast:   Smaller/cheaper model for mechanical prompts (naming, labeling).
    """
    strong: ModelConfig
    fast: ModelConfig


class RetrievalConfig(BaseModel):
    """Vector-search parameters.

    Attributes:
        top_k:          Maximum candidates to retrieve per query.
        ivfflat_probes: IVFFlat lists probed per query (index built with lists=100).
    """
    top_k: int
    ivfflat_probes: int


class SplitConfig(BaseModel):
    """Dataset-generation split parameters.

    Attributes:
        mini_size: Number of rows in the mini subset.
        eval_frac: Fraction reserved for evaluation holdout.
        seed:      Random seed for the split.
    """
    mini_size: int
    eval_frac: float
    seed: int


class RepresentationConfig(BaseModel):
    """Embedding model configuration.

    Attributes:
        model:         Sentence-transformer model identifier.
        embedding_dim: Embedding vector dimensionality.
    """
    model: str
    embedding_dim: int


class BaseClusteringConfig(BaseModel):
    """HDBSCAN parameters for the offline base cluster snapshot.

    Attributes:
        algorithm:                Clustering algorithm name (``"hdbscan"``).
        min_cluster_size:         Minimum points to form a cluster.
        min_samples:              HDBSCAN min_samples (controls noise tolerance).
        cluster_selection_method: ``"eom"`` or ``"leaf"``.
        cluster_selection_epsilon: Distance threshold for cluster merging.
        prob_threshold:           Minimum soft-membership probability to persist.
    """
    algorithm: str = "hdbscan"
    min_cluster_size: int = 50
    min_samples: int = 10
    cluster_selection_method: str = "eom"
    cluster_selection_epsilon: float = 0.0
    prob_threshold: float = 0.01


class OnlineClusteringConfig(BaseModel):
    """HDBSCAN parameters for online drill-down and recut operations.

    Attributes:
        drilldown_min_cluster_size: min_cluster_size for sub-clustering a cluster.
        recut_min_cluster_size:     min_cluster_size for full re-clustering.
    """
    drilldown_min_cluster_size: int = 10
    recut_min_cluster_size: int = 30


class ClusteringConfig(BaseModel):
    """Top-level clustering configuration.

    Attributes:
        base:   Parameters for the offline root cluster snapshot.
        online: Parameters for interactive drill-down and recut.
    """
    base: BaseClusteringConfig = BaseClusteringConfig()
    online: OnlineClusteringConfig = OnlineClusteringConfig()


class FusionConfig(BaseModel):
    """Weights for fusing text, review, and trailer embeddings.

    Attributes:
        text_weight:    Weight applied to the composite_text embedding (0–1).
        review_weight:  Weight applied to the review embedding (0–1).
        trailer_weight: Weight applied to the CLIP trailer embedding (0–1).
                        Set to 0.0 (default) to disable trailer fusion.
    """
    text_weight: float = 0.6
    review_weight: float = 0.4
    trailer_weight: float = 0.0


class UmapConfig(BaseModel):
    """UMAP 2D projection parameters for offline visualization coordinates.

    Attributes:
        n_neighbors: UMAP neighbourhood size.
        min_dist:    Minimum distance between points in the projected space.
    """
    n_neighbors: int = 15
    min_dist: float = 0.1


class ConversationConfig(BaseModel):
    """Per-conversation runtime limits.

    Attributes:
        cost_limit_usd: Maximum USD spend allowed for one conversation.
        max_messages:   Hard message budget before the conversation is closed.
    """
    cost_limit_usd: float = 5.0
    max_messages: int = 100


class IngestionArtifacts(BaseModel):
    """Timestamped parquet paths in the HF dataset repo.

    Attributes:
        snapshot:     Stage-1 cleaned catalogue parquet (no embeddings).
        main:         Stage-2 full production parquet with embeddings.
        mini:         Stage-2 dev subset parquet with embeddings.
        eval_holdout: Stage-2 disjoint evaluation parquet.
    """
    snapshot: str
    main: str
    mini: str
    eval_holdout: str


class IngestionConfig(BaseModel):
    """Hugging Face artifact source for catalogue ingestion.

    Attributes:
        hf_repo:   HF dataset repo id.
        artifacts: Per-split filenames inside the repo.
    """
    hf_repo: str
    artifacts: IngestionArtifacts


class Settings(BaseModel):
    """Full typed configuration loaded from a YAML config file.

    Attributes:
        models:         Two-tier LLM model parameters.
        retrieval:      Vector-search parameters.
        split:          Dataset-generation split parameters.
        representation: Embedding model configuration.
        clustering:     HDBSCAN base + online parameters.
        fusion:         Embedding fusion weights.
        umap:           UMAP 2D projection parameters.
        conversation:   Per-conversation limits.
        ingestion:      HF artifact source.
    """
    models: ModelTiers
    retrieval: RetrievalConfig
    split: SplitConfig
    representation: RepresentationConfig
    clustering: ClusteringConfig = ClusteringConfig()
    fusion: FusionConfig = FusionConfig()
    umap: UmapConfig = UmapConfig()
    conversation: ConversationConfig = ConversationConfig()
    ingestion: IngestionConfig


class EnvSettings(BaseSettings):
    """Typed environment settings loaded from the environment and ``.env`` file.

    Attributes:
        database_url:       Postgres connection string.
        auth_secret:        Secret key for JWT signing.
        jwt_ttl_seconds:    JWT time-to-live in seconds.
        openai_api_key:     OpenAI API key.
        openrouter_api_key: OpenRouter API key.
        hf_token:           Hugging Face token (private repos).
        tmdb_api_key:       TMDB API key (scrape only).
        log_level:          Root logging level (default ``INFO``).
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

    Returns:
        A validated ``EnvSettings`` instance.
    """
    return EnvSettings()


def prompts_dir(agent: str) -> Path:
    """Return the prompts directory for the named agent module.

    Args:
        agent: Agent module name under ``backend/agents/``,
               e.g. ``"intent"``, ``"concept"``.

    Returns:
        ``Path`` to ``backend/agents/<agent>/prompts/``.
    """
    return BACKEND_DIR / "agents" / agent / "prompts"


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
