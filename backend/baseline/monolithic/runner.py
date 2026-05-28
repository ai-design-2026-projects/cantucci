"""Monolithic baseline system handler.

One LLM call per turn using the system-under-test model family. The LLM
proposes the full cluster partition directly; no intent/labeling/concept agents.
"""
import logging
import uuid

from backend.agents.coordinator.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.coordinator.types import TurnTrace, sentinel_cluster_snapshot_id
from backend.baseline.monolithic.agent import monolithic_turn
from backend.baseline.shared.types import SystemTurnResult
from backend.data_access.cluster_snapshots.queries import (
    canonicalize_params,
    create_cluster,
    create_cluster_snapshot,
    create_memberships,
    record_conversation_snapshot_ref,
)
from backend.data_access.conversations.queries import (
    get_conversation,
    set_current_cluster_snapshot,
)
from backend.data_access.movies.queries import fetch_stubs
from backend.data_access.conversations.types import ConversationRow
from backend.settings import get_config_hash

log = logging.getLogger(__name__)


def _persist_monolithic_snapshot(
    conversation_id: uuid.UUID,
    clusters_proposal: list,
    known_movie_ids: set[int],
    current_snapshot_id: uuid.UUID | None,
) -> uuid.UUID:
    """Persist a cluster snapshot from the LLM's cluster proposal.

    Filters out movie IDs not in *known_movie_ids* to ignore hallucinated IDs.
    Creates one cluster per proposed entry; assigns a uniform probability of 1.0
    (hard assignment) to all members.

    Args:
        conversation_id:    UUID of the conversation.
        clusters_proposal:  List of MonolithicCluster objects from the LLM.
        known_movie_ids:    Set of valid movie IDs (from the previous snapshot).
        current_snapshot_id: Parent snapshot ID for lineage tracking.

    Returns:
        UUID of the newly created cluster snapshot.
    """
    config_hash = get_config_hash()
    snapshot_id = create_cluster_snapshot(
        operation="monolithic",
        params=canonicalize_params({"condition": "monolithic"}),
        config_hash=config_hash,
        parent_id=current_snapshot_id,
    )

    for proposal in clusters_proposal:
        valid_ids = [mid for mid in proposal.movie_ids if mid in known_movie_ids]
        if not valid_ids:
            continue

        exemplar_ids = valid_ids[:8]
        cluster_id = create_cluster(
            cluster_snapshot_id=snapshot_id,
            label=proposal.label,
            summary=proposal.summary,
            exemplar_movie_ids=exemplar_ids,
            parent_cluster_id=None,
        )
        memberships: list[tuple[uuid.UUID, int, float]] = [
            (cluster_id, mid, 1.0) for mid in valid_ids
        ]
        create_memberships(memberships)

    record_conversation_snapshot_ref(conversation_id, snapshot_id)
    set_current_cluster_snapshot(conversation_id, snapshot_id)
    log.info(
        "monolithic_snapshot_persisted",
        extra={
            "conversation_id": str(conversation_id),
            "n_clusters": len(clusters_proposal),
            "snapshot_id": str(snapshot_id),
        },
    )
    return snapshot_id


class MonolithicHandler:
    """Implements the session-driver turn protocol for the monolithic baseline."""

    async def handle_turn(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        conversation_row: ConversationRow,
    ) -> SystemTurnResult:
        """Run one monolithic LLM turn and persist the proposed clustering.

        Args:
            conversation_id: UUID of the active conversation.
            user_message:    Oracle message (included in conversation context).
            conversation_row: Current conversation row.

        Returns:
            ``SystemTurnResult`` with the new snapshot ID and a monolithic TurnTrace.
        """
        current_snapshot_id = conversation_row.current_cluster_snapshot_id
        accumulated_cost = conversation_row.accumulated_cost_usd

        from backend.data_access.cluster_snapshots.queries import get_snapshot_members
        known_movie_ids: set[int] = set()
        if current_snapshot_id is not None:
            members = get_snapshot_members(current_snapshot_id)
            known_movie_ids = {m.movie_id for m in members}

        parsed, cost = await monolithic_turn(
            conversation_id=conversation_id,
            current_cluster_snapshot_id=current_snapshot_id,
            accumulated_cost=accumulated_cost,
        )

        if parsed.clusters and known_movie_ids:
            new_snapshot_id = _persist_monolithic_snapshot(
                conversation_id=conversation_id,
                clusters_proposal=parsed.clusters,
                known_movie_ids=known_movie_ids,
                current_snapshot_id=current_snapshot_id,
            )
        else:
            new_snapshot_id = current_snapshot_id or sentinel_cluster_snapshot_id()

        trace = TurnTrace(
            modes=["monolithic"],
            concepts=[None],
            target_cluster_ids=[None],
            confidence=1.0,
            clarifier_fired=False,
            raw_intent="{}",
            suggestion=None,
            explanation=None,
        )

        return SystemTurnResult(
            reply_text=parsed.reply,
            cluster_snapshot_id=new_snapshot_id,
            turn_cost_usd=cost,
            suggestion=None,
            turn_trace=trace,
        )
