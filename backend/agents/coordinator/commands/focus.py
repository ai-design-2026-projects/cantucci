import logging
import uuid
from dataclasses import dataclass
from typing import ClassVar

from backend.agents.coordinator.commands._helpers import _persist_draft
from backend.agents.coordinator.commands.base import ActionResult, ExecutionContext
from backend.agents.coordinator.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.responder import replies
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters, get_snapshot_members
from backend.settings import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FocusCommand:
    """Narrow the snapshot to a single cluster's members, dropping all others.

    Attributes:
        target_cluster_id: Cluster to keep; falls back to the first cluster when None.
        confidence:        LLM confidence [0, 1].
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = True
    CREATES_SNAPSHOT: ClassVar[bool] = True
    READS_CLUSTERS: ClassVar[bool] = True

    target_cluster_id: uuid.UUID | None
    confidence: float

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Focus the working set on one cluster.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reply, new snapshot id, and cost.
        """
        target_id = self.target_cluster_id or (ctx.clusters[0].id if ctx.clusters else None)
        if target_id is None:
            return ActionResult(
                reply_fragment=replies.NO_CLUSTER_TO_SPLIT,
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        target_cluster = next((c for c in ctx.clusters if c.id == target_id), None)
        ctx.reporter.step("clustering")
        draft = await focus(
            source_cluster_id=target_id,
            parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        )
        new_snapshot_id, step_cost, _, _ = await _persist_draft(ctx, draft)
        n_members = len({mid for mid, _ in draft.clusters[0].memberships}) if draft.clusters else 0
        label = target_cluster.label if target_cluster else None
        return ActionResult(
            reply_fragment=replies.format_focus_reply(label, n_members),
            cluster_snapshot_id=new_snapshot_id,
            step_cost=step_cost,
        )


async def focus(
    source_cluster_id: uuid.UUID,
    parent_cluster_snapshot_id: uuid.UUID,
) -> ClusterSnapshotDraft:
    """Narrow the working set to a single cluster, discarding all other points.

    Produces a snapshot containing exactly one cluster — the selected cluster's
    members under its existing label. All other clusters in the parent snapshot
    are dropped. No HDBSCAN or LLM call is made.

    A follow-up ``recut`` or ``drill_down`` on the resulting snapshot will
    operate only on the focused subset.

    Args:
        source_cluster_id:          Cluster to keep.
        parent_cluster_snapshot_id: Snapshot the cluster belongs to.

    Returns:
        ``ClusterSnapshotDraft`` with a single cluster.

    Raises:
        ValueError: If the source cluster has no members or is not found in the snapshot.
    """
    from backend.agents.coordinator.commands._clustering import exemplars

    cswc = get_cluster_snapshot_with_clusters(parent_cluster_snapshot_id)
    if cswc is None:
        raise ValueError(f"Cluster snapshot {parent_cluster_snapshot_id} not found")

    # Find the source cluster in the snapshot
    source = next((cluster for cluster in cswc.clusters if cluster.id == source_cluster_id), None)
    if source is None:
        raise ValueError(f"Cluster {source_cluster_id} not found in snapshot {parent_cluster_snapshot_id}")

    # Get the members of the source cluster. They are defined as the datapoints
    # in the parent snapshot whose argmax cluster is the source cluster, scoped
    # to that snapshot to avoid cross-snapshot probability contamination.
    all_members = get_snapshot_members(parent_cluster_snapshot_id)
    memberships_rows = [m for m in all_members if m.cluster_id == source_cluster_id]
    if not memberships_rows:
        raise ValueError(f"Cluster {source_cluster_id} has no members")

    cfg = get_settings()
    members = [(movie.movie_id, movie.probability) for movie in memberships_rows]
    mids = [movie[0] for movie in members]
    prbs = [movie[1] for movie in members]

    cluster = ClusterDraft(
        label=source.label or "Focused",
        summary=source.summary,
        exemplar_movie_ids=exemplars(mids, prbs, cfg.labeling.top_exemplars),
        parent_cluster_id=source_cluster_id,
        memberships=members,
    )

    params: dict = {
        "operation": "focus",
        "source_cluster_id": str(source_cluster_id),
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id),
    }
    log.info("focus_complete", extra={"source_cluster_id": str(source_cluster_id), "n_members": len(members)})
    return ClusterSnapshotDraft(operation="focus", params=params, clusters=[cluster])
