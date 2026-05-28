from dataclasses import dataclass
from typing import ClassVar

from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.agents.responder import replies


@dataclass(frozen=True, slots=True)
class SmallTalkCommand:
    """Handle a casual message with no clustering operation.

    Attributes:
        confidence: LLM confidence [0, 1].
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = False
    CREATES_SNAPSHOT: ClassVar[bool] = False
    READS_CLUSTERS: ClassVar[bool] = False

    confidence: float

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Return a static help reply.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with static reply and unchanged snapshot.
        """
        return ActionResult(
            reply_fragment=replies.SMALL_TALK,
            cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            step_cost=0.0,
        )
