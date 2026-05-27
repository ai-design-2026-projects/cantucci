"""Offline eval harness configuration loader.

Reads the ``eval_harness:`` section of ``eval/eval.yaml``.  This section is
intentionally absent from ``backend/settings.py`` — it is only relevant to
offline eval scripts, not the runtime system.
"""
import functools
from dataclasses import dataclass
from pathlib import Path

import yaml

_EVAL_YAML_PATH = Path(__file__).parent / "eval.yaml"


@dataclass(frozen=True, slots=True)
class EvalModelConfig:
    """LLM model parameters for an eval-harness agent (oracle or judge).

    Attributes:
        name:           Model identifier string.
        provider:       API provider (e.g. ``"openrouter"``).
        seed:           RNG seed for reproducible completions.
        max_tokens:     Maximum completion tokens per call.
        cost_limit_usd: Per-call cost ceiling in USD.
        dry_run:        When True every harness call short-circuits to a fixture response.
    """
    name: str
    provider: str
    seed: int
    max_tokens: int
    cost_limit_usd: float
    dry_run: bool


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    """Oracle session runner knobs.

    Attributes:
        max_turns: Maximum oracle turns before the runner terminates a simulated session.
    """
    max_turns: int


@dataclass(frozen=True, slots=True)
class ScorerConfig:
    """Deterministic scoring knobs.

    Attributes:
        dimensions:          Ordered list of LLM-judge dimension names.
        silhouette_metric:   Distance metric passed to ``sklearn.metrics.silhouette_score``.
        noise_prob_threshold: Membership probability below which a movie is counted as noise.
    """
    dimensions: list[str]
    silhouette_metric: str
    noise_prob_threshold: float


@dataclass(frozen=True, slots=True)
class GTBuilderConfig:
    """Ground-truth trajectory builder knobs.

    Attributes:
        max_movies: Catalogue movies sampled per build call.
        min_ops:    Minimum operations in a generated trajectory.
        max_ops:    Maximum operations in a generated trajectory.
    """
    max_movies: int
    min_ops: int
    max_ops: int


@dataclass(frozen=True, slots=True)
class EvalHarnessConfig:
    """All offline eval settings from the ``eval_harness:`` section of eval/eval.yaml.

    Attributes:
        oracle:     Oracle simulation model config.
        judge:      LLM-judge model config.
        runner:     Session runner knobs.
        scorer:     Deterministic scoring knobs.
        gt_builder: Ground-truth builder knobs.
    """
    oracle: EvalModelConfig
    judge: EvalModelConfig
    runner: RunnerConfig
    scorer: ScorerConfig
    gt_builder: GTBuilderConfig


@functools.cache
def load_eval_harness_config() -> EvalHarnessConfig:
    """Load the ``eval_harness:`` section from eval/eval.yaml (cached).

    Returns:
        ``EvalHarnessConfig`` populated from eval/eval.yaml.

    Raises:
        FileNotFoundError: If eval/eval.yaml does not exist.
        KeyError:          If the ``eval_harness:`` section or required keys are absent.
    """
    if not _EVAL_YAML_PATH.exists():
        raise FileNotFoundError(f"eval config not found: {_EVAL_YAML_PATH}")
    data = yaml.safe_load(_EVAL_YAML_PATH.read_bytes())
    section = data["eval_harness"]

    def _model(d: dict) -> EvalModelConfig:
        return EvalModelConfig(
            name=d["name"],
            provider=d["provider"],
            seed=d["seed"],
            max_tokens=d["max_tokens"],
            cost_limit_usd=d["cost_limit_usd"],
            dry_run=d.get("dry_run", False),
        )

    runner = section["runner"]
    scorer = section["scorer"]
    gt = section["gt_builder"]
    return EvalHarnessConfig(
        oracle=_model(section["oracle"]),
        judge=_model(section["judge"]),
        runner=RunnerConfig(max_turns=runner["max_turns"]),
        scorer=ScorerConfig(
            dimensions=scorer["dimensions"],
            silhouette_metric=scorer["silhouette_metric"],
            noise_prob_threshold=scorer["noise_prob_threshold"],
        ),
        gt_builder=GTBuilderConfig(
            max_movies=gt["max_movies"],
            min_ops=gt["min_ops"],
            max_ops=gt["max_ops"],
        ),
    )
