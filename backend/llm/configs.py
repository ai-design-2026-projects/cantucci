"""Experimental-condition config loader for the cantucci backend.

Each experimental condition (A–D) is a YAML file in ``configs/`` at the
repository root.  Loading a config returns the parsed dict and a stable hash
of the raw file bytes (used for session reproducibility auditing).

Usage::

    from backend.configs import load_config

    cfg, config_hash = load_config("condition_a")
    model = cfg["model"]["name"]
    seed  = cfg["model"]["seed"]
"""

import hashlib
from pathlib import Path
from typing import Any

import yaml

_CONFIGS_DIR = Path(__file__).parents[1] / "configs"


def load_config(name: str) -> tuple[dict[str, Any], str]:
    """Load a YAML config file and return its content and a stable byte hash.

    The hash is computed on the *raw file bytes* before YAML parsing, so it is
    invariant to round-trip serialisation and whitespace normalisation.

    Args:
        name: Config file stem without extension, e.g. ``"condition_a"``.
              The file ``configs/{name}.yaml`` must exist.

    Returns:
        A tuple ``(config_dict, sha256_8char_prefix)``.

    Raises:
        FileNotFoundError: If ``configs/{name}.yaml`` does not exist.
        yaml.YAMLError: If the file contains invalid YAML.
    """
    path = _CONFIGS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()[:8]
    config: dict[str, Any] = yaml.safe_load(raw_bytes)
    return config, digest
