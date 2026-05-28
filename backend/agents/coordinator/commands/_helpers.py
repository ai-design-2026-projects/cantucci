from backend.agents.coordinator.commands.base import ExecutionContext
from backend.agents.coordinator.tools.persist import persist_and_label
from backend.agents.intent.types import PartitionAttribute
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters

_NUMERIC_ATTRIBUTES = {
    PartitionAttribute.RUNTIME,
    PartitionAttribute.RELEASE_YEAR,
    PartitionAttribute.VOTE_AVERAGE,
}


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
