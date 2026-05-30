import uuid

from backend.coordinator.commands.base import ExecutionContext
from backend.coordinator.tools.persist import persist_and_label
from backend.coordinator.types import ClusterDraft
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.cluster_snapshots.types import ClusterRow


async def persist_draft(ctx: ExecutionContext, draft, base_cost: float = 0.0):
    """Persist a cluster snapshot draft and return (new_snapshot_id, total_cost, n_movies, new_clusters).

    Args:
        ctx:       Execution context carrying conversation and cost state.
        draft:     ``ClusterSnapshotDraft`` to persist.
        base_cost: Additional cost to add to the labeling cost (e.g. from a prior agent call).

    Returns:
        Tuple of (new_snapshot_id, total_cost, n_movies, new_clusters).
    """
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
    from backend.coordinator.commands.helpers.clustering import exemplars

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
