from enum import Enum


class ConversationMode(str, Enum):
    """Adaptive conversation mode derived from the current state of the conversation.

    Attributes:
        EXPLORATION:   Few cluster snapshots, broad questions — encourage discovery.
        REFINEMENT:    Multiple drill-downs observed — optimize cluster snapshots.
        RECOMMENDATION: Narrow cluster count with high acceptance — surface movies.
    """
    EXPLORATION = "exploration"
    REFINEMENT = "refinement"
    RECOMMENDATION = "recommendation"


def select_mode(n_cluster_snapshots: int, n_clusters: int) -> ConversationMode:
    """Deterministically select a conversation mode based on observable state.

    Rules:
    - 1 cluster snapshot (only root): EXPLORATION
    - ≤ 4 clusters in current cluster snapshot: RECOMMENDATION
    - otherwise: REFINEMENT

    Args:
        n_cluster_snapshots: Total number of cluster snapshots in the conversation so far.
        n_clusters:          Number of clusters in the current cluster snapshot.

    Returns:
        The selected ``ConversationMode``.
    """
    if n_cluster_snapshots <= 1:
        return ConversationMode.EXPLORATION
    if n_clusters <= 4:
        return ConversationMode.RECOMMENDATION
    return ConversationMode.REFINEMENT
