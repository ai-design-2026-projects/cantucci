from dataclasses import dataclass
from typing import ClassVar

from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.coordinator.tools.labeling import label_unlabeled_clusters
from backend.coordinator.types import sentinel_cluster_snapshot_id
from backend.agents.responder import replies
from backend.data_access.cluster_snapshots.queries import (
    get_cluster_snapshot_with_clusters,
    get_root_cluster_snapshot,
    record_conversation_snapshot_ref,
)
from backend.data_access.conversations.queries import set_current_cluster_snapshot


@dataclass(frozen=True, slots=True)
class GoToBaseCommand:
    """Navigate to the pre-computed ingest-time base cluster snapshot.

    Attributes:
        confidence: LLM confidence [0, 1].
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = False
    CREATES_SNAPSHOT: ClassVar[bool] = True
    READS_CLUSTERS: ClassVar[bool] = False

    confidence: float

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Navigate to the root snapshot, labeling any unlabeled clusters.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reply, root snapshot id, and labeling cost.
        """
        root = get_root_cluster_snapshot()
        if root is None:
            return ActionResult(
                reply_fragment=replies.NO_BASE_SNAPSHOT,
                cluster_snapshot_id=sentinel_cluster_snapshot_id(),
                step_cost=0.0,
            )
        set_current_cluster_snapshot(ctx.conversation_id, root.id)
        record_conversation_snapshot_ref(ctx.conversation_id, root.id)
        cswc = get_cluster_snapshot_with_clusters(root.id)
        clusters = cswc.clusters if cswc else []
        label_cost = 0.0
        if any(c.label is None for c in clusters):
            ctx.reporter.step("labeling")
            clusters, label_cost = await label_unlabeled_clusters(
                clusters, ctx.conversation_id, ctx.message_id, ctx.accumulated_cost
            )
        return ActionResult(
            reply_fragment=replies.format_reset_reply(len(clusters)),
            cluster_snapshot_id=root.id,
            step_cost=label_cost,
        )
