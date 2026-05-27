from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class OpSpec:
    """A single operation in a ground truth trajectory.

    Attributes:
        op:      Operation type string (drill_down | merge | focus | cross_filter).
        concept: Semantic concept string describing what to operate on.
    """
    op: str
    concept: str


class TrajectoryProposal(BaseModel):
    """LLM output for the trajectory-building pass.

    Attributes:
        operations: Ordered list of operation proposals.
    """
    operations: list[dict[str, str]]


class IntentDescriptionProposal(BaseModel):
    """LLM output for the intent-description writing pass.

    Attributes:
        text: Neutral single-paragraph intent description paraphrasing the trajectory.
    """
    text: str
