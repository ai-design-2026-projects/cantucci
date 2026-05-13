"""Decision Agent result types.

The Decision Agent returns a routing signal consumed by the Orchestrator
to drive the next conversation step (architecture.md §Decision Agent).
"""

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class DecisionAction(str, Enum):
    """Routing action returned by the Decision Agent.

    recommend  — present a recommendation / cluster set to the oracle.
    continue_  — pose a clarifying question before showing results.
                 Named with a trailing underscore because ``continue`` is a
                 Python keyword; the serialised value is still ``"continue"``.
    """

    recommend = "recommend"
    continue_ = "continue"


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
    """

    action: DecisionAction
    best_cluster_id: UUID | None
    rationale: str
    entropy_score: float
