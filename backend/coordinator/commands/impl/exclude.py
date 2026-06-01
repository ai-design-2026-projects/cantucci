import logging
import uuid
from dataclasses import dataclass
from typing import ClassVar

from backend.coordinator.commands.helpers.drafts import persist_draft
from backend.coordinator.commands.helpers.targets import resolve_target_or_clarify
from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.coordinator.tools.clarification_state import mark_awaiting
from backend.coordinator.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.responder import replies
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters, get_snapshot_members
from backend.settings import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExcludeCommand:
    """Drop one cluster from the snapshot, keeping all others.

    Inverse of FocusCommand.

    Attributes:
        target_cluster_id: Cluster to drop.
        confidence:        LLM confidence [0, 1].
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = True
    CREATES_SNAPSHOT: ClassVar[bool] = True
    READS_CLUSTERS: ClassVar[bool] = True

    target_cluster_id: uuid.UUID | None
    confidence: float

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Exclude one cluster from the working set.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reply, new snapshot id, and cost.
        """
        target_id = resolve_target_or_clarify(ctx, self.target_cluster_id)
        if target_id is None and ctx.clusters:
            mark_awaiting(ctx.conversation_id)
            return ActionResult(
                reply_fragment=replies.format_cluster_clarification([c.label for c in ctx.clusters]),
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )
        if target_id is None:
            return ActionResult(
                reply_fragment=replies.NO_CLUSTER_TO_SPLIT,
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        target_cluster = next((c for c in ctx.clusters if c.id == target_id), None)
        label = target_cluster.label if target_cluster else None

        ctx.reporter.step("clustering")
        try:
            draft = await exclude_cluster(
                source_cluster_id=target_id,
                parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            )
        except ValueError as exc:
            if "Cannot exclude the only cluster" in str(exc):
                return ActionResult(
                    reply_fragment=replies.CANNOT_EXCLUDE_ONLY_CLUSTER,
                    cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                    step_cost=0.0,
                )
            raise
        new_snapshot_id, step_cost, _, _ = await persist_draft(ctx, draft)
        n_remaining = len(draft.clusters)
        return ActionResult(
            reply_fragment=replies.format_exclude_reply(label, n_remaining),
            cluster_snapshot_id=new_snapshot_id,
            step_cost=step_cost,
        )


async def exclude_cluster(
    source_cluster_id: uuid.UUID,
    parent_cluster_snapshot_id: uuid.UUID,
) -> ClusterSnapshotDraft:
    """Remove one cluster from the working set, keeping all other clusters intact.

    The inverse of ``focus``: produces a snapshot containing every cluster in the
    parent snapshot *except* the selected one.  All other clusters retain their
    existing labels, summaries, and memberships.  No HDBSCAN or LLM call is made.

    Args:
        source_cluster_id:          Cluster to discard.
        parent_cluster_snapshot_id: Snapshot the cluster belongs to.

    Returns:
        ``ClusterSnapshotDraft`` with all clusters except the excluded one.

    Raises:
        ValueError: If the source cluster is not found, if the snapshot is not found,
                    or if the source is the only cluster (nothing would remain).
    """
    from backend.coordinator.commands.helpers.clustering import exemplars

    cswc = get_cluster_snapshot_with_clusters(parent_cluster_snapshot_id)
    if cswc is None:
        raise ValueError(f"Cluster snapshot {parent_cluster_snapshot_id} not found")

    source = next((c for c in cswc.clusters if c.id == source_cluster_id), None)
    if source is None:
        raise ValueError(f"Cluster {source_cluster_id} not found in snapshot {parent_cluster_snapshot_id}")

    remaining = [c for c in cswc.clusters if c.id != source_cluster_id]
    if not remaining:
        raise ValueError(f"Cannot exclude the only cluster in snapshot {parent_cluster_snapshot_id}")

    cfg = get_settings()
    all_members = get_snapshot_members(parent_cluster_snapshot_id)

    drafts: list[ClusterDraft] = []
    for cluster in remaining:
        memberships_rows = [(m.movie_id, m.probability) for m in all_members if m.cluster_id == cluster.id]
        mids = [m[0] for m in memberships_rows]
        prbs = [m[1] for m in memberships_rows]
        drafts.append(
            ClusterDraft(
                label=cluster.label,
                summary=cluster.summary,
                exemplar_movie_ids=exemplars(mids, prbs, cfg.labeling.top_exemplars),
                parent_cluster_id=cluster.id,
                memberships=memberships_rows,
                color_slot=cluster.color_slot,
            )
        )

    params: dict = {
        "operation": "exclude",
        "source_cluster_id": str(source_cluster_id),
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id),
    }
    log.info(
        "exclude_complete",
        extra={
            "source_cluster_id": str(source_cluster_id),
            "n_remaining": len(drafts),
        },
    )
    return ClusterSnapshotDraft(operation="exclude", params=params, clusters=drafts)
