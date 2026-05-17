"""Decision Agent result types.

The Decision Agent returns a routing signal consumed by the Orchestrator
to drive the next conversation step (architecture.md §Decision Agent).
"""

from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class DecisionAction(str, Enum):
    """Routing action returned by the Decision Agent.

    recommend  — present a recommendation / cluster set to the oracle.
    continue_  — pose a clarifying question before showing results.
                 Named with a trailing underscore because ``continue`` is a
                 Python keyword; the serialised value is still ``"continue"``.
    """

    recommend = "recommend"
    continue_ = "continue"


class DecisionQuestion(BaseModel):
    """Clarifying question emitted when the decision action is ``continue``.

    Attributes:
        text:         The question text to surface to the oracle.
        cluster_refs: Integer indices (0-based) of the clusters this question
                      targets. Mapped back to UUIDs in decision_agent.
    """

    text: str = Field(min_length=1)
    cluster_refs: list[int] = Field(default_factory=list)


class DecisionResponse(BaseModel):
    """Pydantic schema enforced on the LLM decision response via ``response_schema``.

    Validated by the harness; carried on ``LLMResponse.parsed``.

    Attributes:
        action:          ``"recommend"`` or ``"continue"``.
        best_cluster_id: Integer index (0-based) of the recommended cluster, or ``None``.
        rationale:       One-sentence explanation of the decision.
        entropy_score:   Uncertainty estimate echoed from the prompt (0 = certain).
        question:        Present iff ``action == "continue"``; ``None`` otherwise.
    """

    action: str
    best_cluster_id: int | None = None
    rationale: str
    entropy_score: float
    question: DecisionQuestion | None = None

    @model_validator(mode="after")
    def _question_iff_continue(self) -> "DecisionResponse":
        """Enforce question presence contract."""
        if self.action == "continue" and self.question is None:
            raise ValueError("'question' is required when action is 'continue'")
        if self.action == "recommend" and self.question is not None:
            raise ValueError("'question' must be null when action is 'recommend'")
        return self


@dataclass
class DecisionResult:
    """Routing signal produced by ``decision_agent.decide()``.

    Attributes:
        action:          Whether to recommend or continue gathering context.
        best_cluster_id: UUID of the cluster the agent considers most relevant,
                         or None when not applicable.
        rationale:       Free-text explanation (used for prompt context).
        entropy_score:   Uncertainty estimate across clusters (0.0 = fully
                         certain, 1.0 = maximum uncertainty).
        question_text:   Clarifying question to surface when action is continue_.
        cluster_refs:    UUIDs of the clusters the question targets.
    """

    action: DecisionAction
    best_cluster_id: UUID | None
    rationale: str
    entropy_score: float
    question_text: str | None = None
    cluster_refs: list[UUID] = field(default_factory=list)
