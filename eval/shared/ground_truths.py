"""Ground-truth spec loader.

A ground truth is a procedurally-built taste target: a curated set of
``gt_movie_ids`` (TMDB IDs) that represent what a persona "would love",
plus a neutral plain-text description derived from those films.

The Oracle sees *only* ``OracleGroundTruthView.description``.  The full
``GroundTruth`` record (including ``gt_movie_ids``) is held by the runner,
which passes it to the metrics module after a session ends.  This separation
is enforced at the type level: the Oracle constructor accepts only the view.
"""

import hashlib
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

log = logging.getLogger(__name__)


class GroundTruth(BaseModel):
    """Full ground-truth record loaded from ``configs/ground_truths/<slug>.yaml``.

    Attributes:
        id:             Kebab-case slug matching the filename stem.
        seed_movie_ids: TMDB IDs of the films sampled from eval_holdout to seed
                        this ground truth (deterministic with builder seed).
        gt_movie_ids:   Expanded set of ~30–50 TMDB IDs that define "success".
        description:    Neutral, voice-agnostic taste paragraph (no persona overlay).
        gt_hash:        SHA-256 8-char prefix of the raw YAML bytes.
    """

    id: str
    seed_movie_ids: list[int]
    gt_movie_ids: list[int]
    description: str
    gt_hash: str

    def oracle_view(self) -> "OracleGroundTruthView":
        """Return a view that exposes only the description to the Oracle.

        Returns:
            ``OracleGroundTruthView`` with ``id`` and ``description`` only.
        """
        return OracleGroundTruthView(id=self.id, description=self.description)


class OracleGroundTruthView(BaseModel):
    """Restricted view of a ground truth exposed to the Oracle agent.

    Never includes ``gt_movie_ids`` or ``seed_movie_ids``.  The Oracle uses
    only ``description`` to drive its conversational behavior.

    Attributes:
        id:          Slug identifying the ground truth (for logging/replay).
        description: Neutral taste paragraph injected into the Oracle's system prompt.
    """

    id: str
    description: str


def load_ground_truth(path: Path) -> GroundTruth:
    """Load and validate a single ground-truth YAML file.

    Args:
        path: Absolute path to the YAML file.

    Returns:
        Validated ``GroundTruth`` instance.

    Raises:
        FileNotFoundError: If the path does not exist.
        pydantic.ValidationError: If required fields are missing or invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {path}")
    raw_bytes = path.read_bytes()
    data: dict[str, Any] = yaml.safe_load(raw_bytes)
    if "gt_hash" not in data:
        data["gt_hash"] = hashlib.sha256(raw_bytes).hexdigest()[:8]
    gt = GroundTruth(**data)
    log.debug("loaded ground truth id=%s gt_hash=%s", gt.id, gt.gt_hash)
    return gt


def load_all_ground_truths(ground_truths_dir: Path) -> list[GroundTruth]:
    """Load every ``*.yaml`` file under *ground_truths_dir*.

    Args:
        ground_truths_dir: Directory containing ground-truth YAML files.

    Returns:
        List of ``GroundTruth`` instances, sorted by ``id``.

    Raises:
        FileNotFoundError: If the directory does not exist.
        ValueError: If no YAML files are found.
    """
    if not ground_truths_dir.is_dir():
        raise FileNotFoundError(f"Ground truths directory not found: {ground_truths_dir}")
    paths = sorted(ground_truths_dir.glob("*.yaml"))
    if not paths:
        raise ValueError(f"No ground truth YAML files found in {ground_truths_dir}")
    return [load_ground_truth(p) for p in paths]
