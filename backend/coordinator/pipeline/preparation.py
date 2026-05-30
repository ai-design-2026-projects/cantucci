import uuid

from backend.coordinator.tools.labeling import label_unlabeled_clusters
from backend.coordinator.tools.progress import ProgressReporter
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.data_access.conversations.types import ConversationRow


async def prepare_turn(
    conversation_id: uuid.UUID,
    conversation_row: ConversationRow,
    reporter: ProgressReporter,
) -> tuple[uuid.UUID | None, float, float, list[ClusterRow], uuid.UUID]:
    """Load conversation state and label any unlabeled clusters.

    Args:
        conversation_id:  Conversation UUID.
        conversation_row: Pre-loaded conversation row.
        reporter:         SSE progress reporter for this turn.

    Returns:
        Tuple of (current_cluster_snapshot_id, accumulated_cost,
        turn_start_cost, clusters, message_id).
    """
    # Load current conversation state
    current_cluster_snapshot_id = conversation_row.current_cluster_snapshot_id
    accumulated_cost = conversation_row.accumulated_cost_usd
    turn_start_cost = accumulated_cost
    current_snapshot = (
        get_cluster_snapshot_with_clusters(current_cluster_snapshot_id)
        if current_cluster_snapshot_id else None
    )
    current_clusters = current_snapshot.clusters if current_snapshot else []
    message_id = uuid.uuid4()

    # Lazy labelling all the unlabeled clusters
    clusters = current_clusters
    if any(cluster.label is None for cluster in current_clusters):
        reporter.step("labeling")
        clusters, label_cost = await label_unlabeled_clusters(
            current_clusters, conversation_id, message_id, accumulated_cost
        )
        accumulated_cost += label_cost

    return current_cluster_snapshot_id, accumulated_cost, turn_start_cost, clusters, message_id
