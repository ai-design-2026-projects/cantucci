import logging
import uuid
from dataclasses import dataclass
from typing import ClassVar

from backend.coordinator.commands.helpers.drafts import persist_draft
from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.coordinator.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.responder import replies
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters, get_memberships
from backend.settings import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MergeCommand:
    """Combine the first two clusters in the current snapshot into one.

    Attributes:
        merged_label: Label to assign to the resulting merged cluster.
        confidence:   LLM confidence [0, 1].
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = True
    CREATES_SNAPSHOT: ClassVar[bool] = True
    READS_CLUSTERS: ClassVar[bool] = True

    merged_label: str | None
    confidence: float

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Merge the first two clusters in the current snapshot.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reply, new snapshot id, and cost.
        """
        if len(ctx.clusters) < 2:
            return ActionResult(
                reply_fragment=replies.FEWER_THAN_TWO_TO_MERGE,
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        label_a = ctx.clusters[0].label or "Unlabeled"
        label_b = ctx.clusters[1].label or "Unlabeled"
        ids_to_merge = [c.id for c in ctx.clusters[:2]]
        ctx.reporter.step("clustering")
        draft = await merge_clusters(
            cluster_ids=ids_to_merge,
            parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            merged_label=f"{label_a} and {label_b}",
        )
        new_snapshot_id, step_cost, _, _ = await persist_draft(ctx, draft)
        return ActionResult(
            reply_fragment=replies.MERGE_REPLY,
            cluster_snapshot_id=new_snapshot_id,
            step_cost=step_cost,
        )


async def merge_clusters(
    cluster_ids: list[uuid.UUID],
    parent_cluster_snapshot_id: uuid.UUID,
    merged_label: str = "Merged",
) -> ClusterSnapshotDraft:
    """Merge multiple clusters into a single cluster, keeping the rest unchanged.

    Args:
        cluster_ids:                List of cluster UUIDs to merge.
        parent_cluster_snapshot_id: Cluster snapshot the clusters belong to.
        merged_label:               Label for the new merged cluster.

    Returns:
        ``ClusterSnapshotDraft`` with the merged cluster and all unchanged clusters.
    """
    from backend.coordinator.commands.helpers.clustering import exemplars

    cswc = get_cluster_snapshot_with_clusters(parent_cluster_snapshot_id)
    if cswc is None:
        raise ValueError(f"Cluster snapshot {parent_cluster_snapshot_id} not found")

    merge_set = set(cluster_ids)
    merged_memberships: dict[int, float] = {}
    unchanged: list[ClusterDraft] = []

    for cluster in cswc.clusters:
        if cluster.id in merge_set:
            for m in get_memberships(cluster.id):
                existing = merged_memberships.get(m.movie_id, 0.0)
                merged_memberships[m.movie_id] = max(existing, m.probability)
        else:
            members = [(m.movie_id, m.probability) for m in get_memberships(cluster.id)]
            unchanged.append(ClusterDraft(
                label=cluster.label,
                summary=cluster.summary,
                exemplar_movie_ids=cluster.exemplar_movie_ids,
                parent_cluster_id=cluster.parent_cluster_id,
                memberships=members,
                color_slot=cluster.color_slot,
            ))

    cfg = get_settings()
    mids = list(merged_memberships.keys())
    prbs = [merged_memberships[m] for m in mids]
    merged_draft = ClusterDraft(
        label=merged_label,
        summary=None,
        exemplar_movie_ids=exemplars(mids, prbs, cfg.labeling.top_exemplars),
        parent_cluster_id=None,
        memberships=list(merged_memberships.items()),
    )

    clusters = unchanged + [merged_draft]
    params: dict = {
        "operation": "merge",
        "merged_cluster_ids": [str(cid) for cid in cluster_ids],
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id),
        "merged_label": merged_label,
    }
    log.info("merge_complete", extra={"n_merged": len(cluster_ids), "remaining_clusters": len(clusters)})
    return ClusterSnapshotDraft(operation="merge", params=params, clusters=clusters)
