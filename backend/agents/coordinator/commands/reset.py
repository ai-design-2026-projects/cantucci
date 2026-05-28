from dataclasses import dataclass
from typing import ClassVar

from backend.agents.coordinator.commands.base import ActionResult, ExecutionContext
from backend.agents.responder import replies
from backend.data_access.conversations.queries import set_current_cluster_snapshot


@dataclass(frozen=True, slots=True)
class ResetCommand:
    """Return the conversation to the unclustered state (no active snapshot).

    Attributes:
        confidence: LLM confidence [0, 1].
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = False
    CREATES_SNAPSHOT: ClassVar[bool] = False
    READS_CLUSTERS: ClassVar[bool] = False

    confidence: float

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Clear the active cluster snapshot.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reset reply and None snapshot.
        """
        set_current_cluster_snapshot(ctx.conversation_id, None)
        return ActionResult(
            reply_fragment=replies.RESET_REPLY,
            cluster_snapshot_id=None,
            step_cost=0.0,
        )
