"""Canonical operation vocabulary and shared types for the evaluation harness.

This is the single source of truth for operation names. The vocabulary is derived
directly from ``backend.agents.intent.types.NavigationMode`` so it can never drift
from what the coordinator actually supports.
"""
from dataclasses import dataclass
from pathlib import Path

from backend.agents.intent.types import NavigationMode

NAVIGATION_OPERATIONS: frozenset[str] = frozenset(m.value for m in NavigationMode)
"""Full set of navigation operation strings the system supports.

Derived from ``NavigationMode`` at import time — adding a new mode there automatically
expands this set. Currently: cluster, merge, focus, cross_filter, exclude.
"""

CONCEPT_KINDS: frozenset[str] = frozenset({"axis", "palette", "open_ended"})
"""Allowed ``kind`` values for an OpSpec that involves a concept."""

CONCEPT_SPACES: frozenset[str] = frozenset({"semantic", "visual"})
"""Allowed ``space`` values for an OpSpec that involves a concept."""

PERSONAS_DIR: Path = Path(__file__).parent / "personas" / "conf"
"""Directory where bundle YAML files are stored (canonical, human-editable)."""


@dataclass(frozen=True, slots=True)
class OpSpec:
    """A single operation in a ground truth trajectory.

    Attributes:
        op:      Operation type string; must be a member of ``NAVIGATION_OPERATIONS``.
        concept: Human-readable concept string (e.g. "atmospheric thrillers").
        kind:    Optional concept kind: ``"axis"``, ``"palette"``, or ``"open_ended"``.
                 ``None`` for plain metadata operations (genre, director, decade…).
        space:   Optional embedding space: ``"semantic"`` or ``"visual"``.
                 Required when ``kind`` is set; ``None`` otherwise.
    """
    op: str
    concept: str
    kind: str | None = None
    space: str | None = None
