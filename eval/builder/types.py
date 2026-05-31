"""Pydantic wire types for the ground-truth bundle builder LLM response."""
from pydantic import BaseModel


class OpProposal(BaseModel):
    """A single proposed operation in a ground truth trajectory.

    Attributes:
        op:      Operation type; must be in NAVIGATION_OPERATIONS.
        concept: Human-readable concept string.
        kind:    Optional concept kind: ``"axis"``, ``"palette"``, or ``"open_ended"``.
        space:   Optional embedding space: ``"semantic"`` or ``"visual"``.
    """
    op: str
    concept: str
    kind: str | None = None
    space: str | None = None


class GroundTruthProposal(BaseModel):
    """Structured LLM output from the ground-truth builder prompt.

    Attributes:
        slug:               Single lowercase word identifying this bundle (e.g. ``"colonialism"``).
        intent_description: Natural-language goal statement for the oracle.
        operations:         Ordered list of proposed operations.
    """
    slug: str
    intent_description: str
    operations: list[OpProposal]
