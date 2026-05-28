"""No-agents baseline pipeline: return the root cluster snapshot unchanged.

This baseline deliberately skips all LLM-backed agents (intent, clustering,
labeling, concept). It uses the pre-computed root HDBSCAN snapshot from
ingestion as the static response to every oracle message, making it a useful
lower bound on navigation quality with zero per-session LLM cost.
"""
import logging
import uuid

from backend.coordinator.types import TurnTrace
from backend.data_access.cluster_snapshots.queries import (
    get_root_cluster_snapshot,
    record_conversation_snapshot_ref,
)
from backend.data_access.conversations.queries import set_current_cluster_snapshot
from backend.coordinator.types import sentinel_cluster_snapshot_id

log = logging.getLogger(__name__)


def get_no_agents_snapshot(conversation_id: uuid.UUID) -> uuid.UUID:
    """Return the root cluster snapshot ID and record a conversation reference.

    Args:
        conversation_id: UUID of the active conversation.

    Returns:
        UUID of the root cluster snapshot. Falls back to the zero sentinel if
        no root snapshot exists yet (e.g. catalogue not ingested).
    """
    root = get_root_cluster_snapshot()
    if root is None:
        log.warning("no_agents_no_root_snapshot", extra={"conversation_id": str(conversation_id)})
        return sentinel_cluster_snapshot_id()

    record_conversation_snapshot_ref(conversation_id, root.id)
    set_current_cluster_snapshot(conversation_id, root.id)
    return root.id


def build_no_agents_trace() -> TurnTrace:
    """Return a TurnTrace marking this turn as a no-agents baseline turn.

    Returns:
        ``TurnTrace`` with modes=["no_agents"], no concepts, and all
        intent fields set to their null equivalents.
    """
    return TurnTrace(
        modes=["no_agents"],
        concepts=[None],
        target_cluster_ids=[None],
        confidence=1.0,
        clarifier_fired=False,
        raw_intent="{}",
        suggestion=None,
        explanation=None,
    )
