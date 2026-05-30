import uuid

from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.coordinator.tools.persist import persist_and_label
from backend.agents.intent.types import PartitionAttribute
from backend.coordinator.types import ClusterDraft
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.cluster_snapshots.types import ClusterRow

_NUMERIC_ATTRIBUTES = {
    PartitionAttribute.RUNTIME,
    PartitionAttribute.RELEASE_YEAR,
    PartitionAttribute.VOTE_AVERAGE,
}


def resolve_target_or_clarify(
    ctx: ExecutionContext, target_cluster_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Resolve a target cluster ID, auto-selecting when exactly one cluster is active.

    Returns a concrete cluster UUID when the target can be determined without user
    input:
      - If ``target_cluster_id`` is already set, return it directly.
      - If exactly one cluster is active, return that cluster's ID (deterministic
        shortcut — no clarification needed when there is no ambiguity).
      - Otherwise return ``None``: the caller should request clarification (2+ clusters)
        or fall back to the whole-catalogue path (0 clusters).

    Args:
        ctx:               Execution context carrying the current cluster list.
        target_cluster_id: Cluster UUID from the intent agent, or ``None`` if not named.

    Returns:
        Resolved cluster UUID, or ``None`` when ambiguous or no clusters exist.
    """
    if target_cluster_id is not None:
        return target_cluster_id
    if len(ctx.clusters) == 1:
        return ctx.clusters[0].id
    return None


def clarify_ambiguous_target(ctx: ExecutionContext) -> ActionResult | None:
    """Return a clarification ActionResult when the target cluster is ambiguous, else None.

    Should be called after ``resolve_target_or_clarify`` returns ``None`` and
    ``ctx.clusters`` is non-empty (2+ clusters exist but none was specified).
    Marks the conversation as awaiting a clarification reply and returns the
    clarification message.  When there are no clusters at all, returns ``None``
    so the caller can fall through to the whole-catalogue path.

    Args:
        ctx: Execution context carrying the current cluster list.

    Returns:
        ``ActionResult`` with the clarification message, or ``None`` when
        ``ctx.clusters`` is empty.
    """
    from backend.agents.responder import replies
    from backend.coordinator.tools.clarification_state import mark_awaiting

    if not ctx.clusters:
        return None
    mark_awaiting(ctx.conversation_id)
    return ActionResult(
        reply_fragment=replies.format_cluster_clarification([c.label for c in ctx.clusters]),
        cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        step_cost=0.0,
    )


async def _persist_draft(ctx: ExecutionContext, draft, base_cost: float = 0.0):
    """Persist a cluster snapshot draft and return (new_snapshot_id, total_cost, n_movies, new_clusters)."""
    new_snapshot_id, label_cost = await persist_and_label(
        draft, ctx.conversation_id, ctx.current_cluster_snapshot_id, ctx.accumulated_cost + base_cost
    )
    total_cost = base_cost + label_cost
    new_cswc = get_cluster_snapshot_with_clusters(new_snapshot_id)
    new_clusters = new_cswc.clusters if new_cswc else []
    n_movies = len({mid for c in draft.clusters for mid, _ in c.memberships})
    return new_snapshot_id, total_cost, n_movies, new_clusters


def draft_from_cluster(
    cluster: ClusterRow,
    memberships: list[tuple[int, float]],
    top_n: int,
    parent_cluster_id: uuid.UUID | None,
    label: str | None = None,
) -> ClusterDraft:
    """Build a ``ClusterDraft`` from an existing cluster row and its pre-loaded memberships.

    Centralises the recurring pattern of rebuilding a ``ClusterDraft`` from a row
    fetched from the DB (used by merge, exclude, focus, and sibling carry-forward).
    The caller is responsible for loading the correct memberships for the cluster;
    this function only handles exemplar selection and ``ClusterDraft`` construction.

    Args:
        cluster:          Source ``ClusterRow`` supplying label, summary, and color_slot.
        memberships:      ``[(movie_id, probability), ...]`` for this cluster.
        top_n:            Maximum number of exemplar IDs (from ``cfg.labeling.top_exemplars``).
        parent_cluster_id: Value to set on ``ClusterDraft.parent_cluster_id``; varies by
                           operation (e.g. ``cluster.id`` for split siblings, ``cluster.parent_cluster_id``
                           for merge unchanged clusters, ``source_cluster_id`` for focus).
        label:            Override the cluster's existing label; pass ``None`` to use
                          ``cluster.label`` unchanged.

    Returns:
        ``ClusterDraft`` ready for inclusion in a ``ClusterSnapshotDraft``.
    """
    from backend.coordinator.commands._clustering import exemplars

    mids = [m[0] for m in memberships]
    prbs = [m[1] for m in memberships]
    return ClusterDraft(
        label=label if label is not None else cluster.label,
        summary=cluster.summary,
        exemplar_movie_ids=exemplars(mids, prbs, top_n),
        parent_cluster_id=parent_cluster_id,
        memberships=memberships,
        color_slot=cluster.color_slot,
    )


def merge_in_siblings(
    parent_cluster_snapshot_id: uuid.UUID | None,
    source_cluster_id: uuid.UUID,
    new_clusters: list[ClusterDraft],
) -> list[ClusterDraft]:
    """Return sibling clusters followed by the new sub-clusters.

    When a split targets a single cluster, the resulting snapshot should carry
    every sibling cluster unchanged plus the new sub-clusters in place of the
    target.  This mirrors the pattern used by ``merge_clusters`` and
    ``exclude_cluster``.

    If ``parent_cluster_snapshot_id`` is ``None`` or the snapshot has no
    clusters other than the target, ``new_clusters`` is returned unchanged
    (full-catalogue splits have no siblings to preserve).

    Args:
        parent_cluster_snapshot_id: Snapshot the source cluster belongs to.
        source_cluster_id:          Cluster being split (will be replaced).
        new_clusters:               Sub-clusters produced by the split.

    Returns:
        List of ``ClusterDraft`` objects: siblings first, then ``new_clusters``.
    """
    from backend.data_access.cluster_snapshots.queries import get_snapshot_members
    from backend.settings import get_settings

    if parent_cluster_snapshot_id is None:
        return new_clusters

    cswc = get_cluster_snapshot_with_clusters(parent_cluster_snapshot_id)
    if cswc is None:
        return new_clusters

    siblings = [c for c in cswc.clusters if c.id != source_cluster_id]
    if not siblings:
        return new_clusters

    cfg = get_settings()
    all_members = get_snapshot_members(parent_cluster_snapshot_id)
    result: list[ClusterDraft] = []
    for cluster in siblings:
        memberships_rows = [(m.movie_id, m.probability) for m in all_members if m.cluster_id == cluster.id]
        result.append(draft_from_cluster(cluster, memberships_rows, cfg.labeling.top_exemplars, cluster.id))
    return result + new_clusters
