import uuid
from dataclasses import dataclass
from typing import ClassVar

from backend.agents.coordinator.commands.base import ActionResult, ExecutionContext
from backend.agents.responder import replies


@dataclass(frozen=True, slots=True)
class ExplainCommand:
    """Explain why a movie belongs in a cluster.

    Attributes:
        target_cluster_id: Cluster whose top exemplar movie to explain;
                           falls back to the first cluster when None.
        confidence:        LLM confidence [0, 1].
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = False
    CREATES_SNAPSHOT: ClassVar[bool] = False
    READS_CLUSTERS: ClassVar[bool] = True

    target_cluster_id: uuid.UUID | None
    confidence: float

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Generate an explanation for the top movie in the target cluster.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with explanation text, unchanged snapshot, and cost.
        """
        from backend.agents.explanation.agent import explain_placement

        ctx.reporter.step("explain")
        target_cluster = (
            next((c for c in ctx.clusters if c.id == self.target_cluster_id), None)
            if self.target_cluster_id else (ctx.clusters[0] if ctx.clusters else None)
        )
        if target_cluster is None or not target_cluster.exemplar_movie_ids:
            return ActionResult(
                reply_fragment=replies.EXPLAIN_TARGET_UNCLEAR,
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        movie_id = target_cluster.exemplar_movie_ids[0]
        result = await explain_placement(
            movie_id=movie_id,
            cluster_id=target_cluster.id,
            cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            conversation_id=ctx.conversation_id,
            message_id=ctx.message_id,
            accumulated_cost=ctx.accumulated_cost,
        )
        return ActionResult(
            reply_fragment=result.text,
            cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            step_cost=result.cost,
        )
