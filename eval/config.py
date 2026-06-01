"""Offline eval harness configuration loader.

Reads the ``eval_harness:`` section of ``eval/eval.yaml``.  This section is
intentionally absent from ``backend/settings.py`` — it is only relevant to
offline eval scripts, not the runtime system.
"""
import functools
from dataclasses import dataclass
from pathlib import Path

import yaml

_EVAL_DIR = Path(__file__).parent
_EVAL_YAML_PATH = _EVAL_DIR / "eval.yaml"


def eval_prompts_dir(module: str) -> Path:
    """Return the prompts directory for the named eval module.

    Args:
        module: Module name under ``eval/``, e.g. ``"oracle"``, ``"judge"``, ``"build"``.

    Returns:
        ``Path`` to ``eval/<module>/prompts/``.
    """
    return _EVAL_DIR / module / "prompts"


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
        max_turns:       Maximum oracle turns before the runner terminates a simulated session.
        exemplar_top_k:  Maximum exemplar movie titles shown per cluster in oracle prompts.
        max_parallel:    Maximum concurrent simulated sessions in a batch run.
        run_seed:        Seed used when auto-creating a run row.
    """
    max_turns: int
    exemplar_top_k: int
    max_parallel: int
    run_seed: int


@dataclass(frozen=True, slots=True)
class ScorerConfig:
    """LLM-judge scoring knobs.

    Attributes:
        dimensions:    Ordered list of LLM-judge dimension names.
        pole_sample_k: Number of film titles sampled from each pole of a concept axis,
                       passed to the judge for ``concept_axis_quality`` scoring.
        exemplar_k:    Maximum exemplar titles shown per cluster in the judge prompt.
    """
    dimensions: list[str]
    pole_sample_k: int
    exemplar_k: int


@dataclass(frozen=True, slots=True)
class GTBuilderConfig:
    """Ground-truth trajectory builder knobs.

    Attributes:
        min_ops: Minimum operations in a generated trajectory.
        max_ops: Maximum operations in a generated trajectory.
    """
    min_ops: int
    max_ops: int


@dataclass(frozen=True, slots=True)
class EvalHarnessConfig:
    """All offline eval settings from the ``eval_harness:`` section of eval/eval.yaml.

    Attributes:
        oracle:     Oracle simulation model config.
        judge:      LLM-judge model config.
        runner:     Session runner knobs.
        scorer:     LLM-judge scoring knobs.
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
        runner=RunnerConfig(
            max_turns=runner["max_turns"],
            exemplar_top_k=runner["exemplar_top_k"],
            max_parallel=runner["max_parallel"],
            run_seed=runner["run_seed"],
        ),
        scorer=ScorerConfig(
            dimensions=scorer["dimensions"],
            pole_sample_k=scorer["pole_sample_k"],
            exemplar_k=scorer["exemplar_k"],
        ),
        gt_builder=GTBuilderConfig(
            min_ops=gt["min_ops"],
            max_ops=gt["max_ops"],
        ),
    )
