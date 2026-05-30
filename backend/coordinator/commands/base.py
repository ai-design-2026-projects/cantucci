import uuid
from typing import ClassVar, Protocol, runtime_checkable
from dataclasses import dataclass

from backend.coordinator.tools.progress import ProgressReporter
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.data_access.conversations.types import ConversationRow


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Return value from Action.execute().
    Attributes:
        cluster_snapshot_id: The ID of the updated cluster snapshot after this action.
        reply_fragment:      Text to append to the turn reply.
        step_cost:           LLM cost incurred during this action in USD.
        axis_concept_id:     UUID of the concept whose normalized scores back a beeswarm
                             axis-distribution proposal.  Non-None only when this action
                             ended with a concept-axis proposal (no snapshot created).
    """
    cluster_snapshot_id: uuid.UUID | None
    reply_fragment: str
    step_cost: float
    axis_concept_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """
    Immutable per-action session state passed to Action.execute().
    Attributes:
        current_cluster_snapshot_id: Active snapshot before this action.
        clusters:                    Current cluster states from the snapshot
        conversation_id:             Conversation UUID.
        conversation_row:            Current conversation state.
        message_id:                  Message UUID for LLM logging.
        accumulated_cost:            Running LLM cost before this action.
        reporter:                    SSE progress reporter for this turn.
    """
    current_cluster_snapshot_id: uuid.UUID | None
    clusters: list[ClusterRow]
    conversation_id: uuid.UUID
    conversation_row: ConversationRow
    message_id: uuid.UUID
    accumulated_cost: float
    reporter: ProgressReporter


@runtime_checkable
class Command(Protocol):
    """
    Protocol every command class must satisfy.
    Class-level metadata flags encode the command's preconditions and effects:
    Attributes:
        REQUIRES_SNAPSHOT: True when the command must have a non-None snapshot
                           to operate (e.g. merge, focus, exclude).
        CREATES_SNAPSHOT:  True when the command navigates to or writes a new
                           snapshot (all navigation modes + go_to_base, undo).
        READS_CLUSTERS:    True when the command's behavior depends on the current cluster state
    """

    REQUIRES_SNAPSHOT: ClassVar[bool]
    CREATES_SNAPSHOT: ClassVar[bool]
    READS_CLUSTERS: ClassVar[bool]

    # NOTE: must be implemented by all subclasses
    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Execute this command and return the result."""
        ...
