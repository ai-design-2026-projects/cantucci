"""
Persona-profile spec loader.

A persona profile is a humanoid behavioral overlay applied on top of any
ground truth.  It controls communication style and conversational dials
(verbosity, decisiveness, drift tendency) but knows nothing about taste
content — that lives in the ground truth.

An eval cell is ``(ground_truth × persona_profile × session_seed)``.  Running
the same ground truth through multiple personas measures whether the system
performs consistently regardless of how the oracle communicates.
"""

import hashlib
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

log = logging.getLogger(__name__)


class PersonaDials(BaseModel):
    """Coarse behavioral dials that seed the ``BehaviorRng``.

    All float fields are clamped to ``[0.0, 1.0]``.

    Attributes:
        verbosity:          Reply length — ``"terse"``, ``"medium"``, or ``"verbose"``.
        decisiveness:       Likelihood to accept a recommendation early (0=explorer, 1=decisive).
        drift_probability:  Per-turn probability that the Oracle introduces a tangent.
        contradiction_rate: Per-turn probability that the Oracle self-contradicts.
    """

    verbosity: str = "medium"
    decisiveness: float = 0.5
    drift_probability: float = 0.0
    contradiction_rate: float = 0.0

    @field_validator("decisiveness", "drift_probability", "contradiction_rate", mode="before")
    @classmethod
    def clamp_to_unit(cls, v: float) -> float:
        """Clamp float dials to [0.0, 1.0].

        Args:
            v: Raw value from YAML.

        Returns:
            Value clamped to [0.0, 1.0].
        """
        return max(0.0, min(1.0, float(v)))

    @field_validator("verbosity", mode="before")
    @classmethod
    def validate_verbosity(cls, v: str) -> str:
        """Validate verbosity is one of the three allowed levels.

        Args:
            v: Raw value from YAML.

        Returns:
            Validated verbosity string.

        Raises:
            ValueError: If not in {terse, medium, verbose}.
        """
        if v not in {"terse", "medium", "verbose"}:
            raise ValueError(f"verbosity must be terse | medium | verbose, got {v!r}")
        return v


class PersonaProfile(BaseModel):
    """Humanoid communication-style overlay for an eval session.

    Attributes:
        id:           Kebab-case slug matching the filename stem.
        name:         Human-readable display name.
        traits:       Free-text personality paragraph injected into the Oracle's
                      system prompt as character guidance.
        dials:        Coarse behavioral dials (used by ``BehaviorRng``).
        persona_hash: SHA-256 8-char prefix of the raw YAML bytes.
    """

    id: str
    name: str
    traits: str
    dials: PersonaDials = PersonaDials()
    persona_hash: str


def load_persona(path: Path) -> PersonaProfile:
    """Load and validate a single persona-profile YAML file.

    Args:
        path: Absolute path to the YAML file.

    Returns:
        Validated ``PersonaProfile`` instance.

    Raises:
        FileNotFoundError: If the path does not exist.
        pydantic.ValidationError: If required fields are missing or invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"Persona file not found: {path}")
    raw_bytes = path.read_bytes()
    data: dict[str, Any] = yaml.safe_load(raw_bytes)
    if "persona_hash" not in data:
        data["persona_hash"] = hashlib.sha256(raw_bytes).hexdigest()[:8]
    profile = PersonaProfile(**data)
    log.debug("loaded persona id=%s persona_hash=%s", profile.id, profile.persona_hash)
    return profile


def load_all_personas(personas_dir: Path) -> list[PersonaProfile]:
    """Load every ``*.yaml`` file under *personas_dir*.

    Args:
        personas_dir: Directory containing persona YAML files.

    Returns:
        List of ``PersonaProfile`` instances, sorted by ``id``.

    Raises:
        FileNotFoundError: If the directory does not exist.
        ValueError: If no YAML files are found.
    """
    if not personas_dir.is_dir():
        raise FileNotFoundError(f"Personas directory not found: {personas_dir}")
    paths = sorted(personas_dir.glob("*.yaml"))
    if not paths:
        raise ValueError(f"No persona YAML files found in {personas_dir}")
    return [load_persona(p) for p in paths]
