from dataclasses import dataclass
from typing import ClassVar

from backend.agents.coordinator.commands.base import ActionResult, ExecutionContext
from backend.agents.coordinator.tools.labeling import label_unlabeled_clusters
from backend.agents.responder import replies
from backend.data_access.cluster_snapshots.queries import (
    get_cluster_snapshot,
    get_cluster_snapshot_with_clusters,
    record_conversation_snapshot_ref,
)
from backend.data_access.conversations.queries import set_current_cluster_snapshot


@dataclass(frozen=True, slots=True)
class UndoCommand:
    """Step back to the parent of the current cluster snapshot.

    Attributes:
        confidence: LLM confidence [0, 1].
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = False
    CREATES_SNAPSHOT: ClassVar[bool] = True
    READS_CLUSTERS: ClassVar[bool] = False

    confidence: float

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Navigate to the parent snapshot, labeling any unlabeled clusters.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reply, parent snapshot id, and labeling cost.
        """
        if ctx.current_cluster_snapshot_id is None:
            return ActionResult(
                reply_fragment=replies.NO_UNDO,
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        current_row = get_cluster_snapshot(ctx.current_cluster_snapshot_id)
        if current_row is None or current_row.parent_id is None:
            return ActionResult(
                reply_fragment=replies.NO_UNDO,
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        parent_id = current_row.parent_id
        set_current_cluster_snapshot(ctx.conversation_id, parent_id)
        record_conversation_snapshot_ref(ctx.conversation_id, parent_id)

        cswc = get_cluster_snapshot_with_clusters(parent_id)
        clusters = cswc.clusters if cswc else []
        label_cost = 0.0
        if any(c.label is None for c in clusters):
            ctx.reporter.step("labeling")
            clusters, label_cost = await label_unlabeled_clusters(
                clusters, ctx.conversation_id, ctx.message_id, ctx.accumulated_cost
            )
        parent_operation = current_row.operation
        return ActionResult(
            reply_fragment=replies.format_undo_reply(parent_operation, len(clusters)),
            cluster_snapshot_id=parent_id,
            step_cost=label_cost,
        )
