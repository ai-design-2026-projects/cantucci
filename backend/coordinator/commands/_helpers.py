import uuid

from backend.coordinator.commands.base import ExecutionContext
from backend.coordinator.tools.persist import persist_and_label
from backend.agents.intent.types import PartitionAttribute
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters

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
