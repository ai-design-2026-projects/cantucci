"""Ambiguity Agent result types."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class AmbiguityQuestion:
    """Clarifying question produced by the Ambiguity Agent.

    Attributes:
        question_text: The focused question to surface to the oracle.
        ui_format:     Rendering hint for the UI (e.g. ``"binary"``,
                       ``"forced_choice"``).
        cluster_refs:  IDs of the 2–3 clusters the question targets.
    """

    question_text: str
    ui_format: str
    cluster_refs: list[UUID] = field(default_factory=list)
