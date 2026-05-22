import logging
import uuid
from dataclasses import dataclass, replace

from backend.agents.clustering.agent import apply_drill_down, apply_merge, apply_recut
from backend.agents.common.strategy import select_mode
from backend.agents.concept.agent import build_concept
from backend.agents.explanation.agent import explain_placement
from backend.agents.intent.agent import classify as classify_intent
from backend.agents.intent.types import NavigationMode
from backend.agents.labeling.agent import label_cluster
from backend.data_access.conversations.queries import get_conversation, get_messages, set_current_cluster_snapshot
from backend.data_access.conversations.types import ConversationRow
from backend.data_access.cluster_snapshots.queries import (
    get_cluster_snapshot_with_clusters,
    get_conversation_cluster_snapshots,
    get_root_cluster_snapshot,
    record_conversation_snapshot_ref,
    update_cluster_label,
)
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.data_access.movies.queries import list_movie_ids

log = logging.getLogger(__name__)


@dataclass
class CoordinatorResult:
    """Output of a single Coordinator.handle_message call.

    Attributes:
        reply_text:          Text to send back to the user.
        cluster_snapshot_id: UUID of the active cluster snapshot after this message.
    """
    reply_text: str
    cluster_snapshot_id: uuid.UUID


class Coordinator:
    """Orchestrates one user message through the agent pipeline.
    Does not hold session state — all state is read from and written to the DB.
    Each call to handle_message is stateless and re-reads current conversation state.
    """

    async def handle_message(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        conversation_row: ConversationRow,
    ) -> CoordinatorResult:
        """Process one user message and return the assistant reply with updated cluster snapshot.

        Pipeline:
          1. Load current cluster snapshot + recent messages.
          2. Classify intent (Intent agent).
          3. Branch on mode: concept → cluster op → persist, or explain, or direct reply.
          4. Generate a reply summarizing what changed.

        Args:
            conversation_id:   Conversation UUID.
            user_message:      Raw user message text.
            conversation_row:  Pre-loaded conversation row (avoids double DB hit).

        Returns:
            ``CoordinatorResult`` with reply text and active cluster snapshot ID.
        """
        current_cluster_snapshot_id = conversation_row.current_cluster_snapshot_id
        accumulated_cost = 0.0

        cswc = get_cluster_snapshot_with_clusters(current_cluster_snapshot_id) if current_cluster_snapshot_id else None
        clusters = cswc.clusters if cswc else []
        all_snapshots = get_conversation_cluster_snapshots(conversation_id)

        message_id = uuid.uuid4()

        if any(c.label is None for c in clusters):
            clusters = await _label_unlabeled_clusters(clusters, conversation_id, message_id, accumulated_cost)

        intent = await classify_intent(
            user_message=user_message,
            clusters=clusters,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
        )
        accumulated_cost += 0.0

        mode = select_mode(len(all_snapshots), len(clusters))
        log.info(
            "coordinator_dispatch",
            extra={
                "conversation_id": str(conversation_id),
                "intent_mode": intent.mode.value,
                "strategy_mode": mode.value,
                "n_clusters": len(clusters),
            },
        )

        if intent.mode == NavigationMode.SMALL_TALK:
            reply = (
                "I'm here to help you explore the movie catalogue through clustering. "
                "You can ask me to split a cluster, merge groups, or explain a placement."
            )
            cluster_snapshot_id = current_cluster_snapshot_id or _sentinel_cluster_snapshot_id()
            return CoordinatorResult(reply_text=reply, cluster_snapshot_id=cluster_snapshot_id)

        if intent.mode == NavigationMode.RESET or current_cluster_snapshot_id is None:
            return await self._handle_reset(conversation_id, conversation_row)

        if intent.mode == NavigationMode.EXPLAIN:
            return await self._handle_explain(
                intent, clusters, current_cluster_snapshot_id, conversation_id, message_id, accumulated_cost
            )

        if intent.mode == NavigationMode.DRILL_DOWN:
            target_id = intent.target_cluster_id or (clusters[0].id if clusters else None)
            if target_id is None:
                return CoordinatorResult(
                    reply_text="Please specify which cluster to split.",
                    cluster_snapshot_id=current_cluster_snapshot_id,
                )
            concept = None
            if intent.concept:
                concept = await build_concept(intent.concept, conversation_id, message_id, accumulated_cost)
            new_cluster_snapshot_id = await apply_drill_down(
                source_cluster_id=target_id,
                parent_cluster_snapshot_id=current_cluster_snapshot_id,
                conversation_id=conversation_id,
                concept=concept,
                accumulated_cost=accumulated_cost,
            )
            new_cswc = get_cluster_snapshot_with_clusters(new_cluster_snapshot_id)
            n_new = len(new_cswc.clusters) if new_cswc else 0
            labels = [c.label for c in (new_cswc.clusters if new_cswc else [])]
            reply = f"Split into {n_new} sub-clusters: {', '.join(labels[:5])}{'…' if n_new > 5 else ''}."
            return CoordinatorResult(reply_text=reply, cluster_snapshot_id=new_cluster_snapshot_id)

        if intent.mode == NavigationMode.MERGE:
            if len(clusters) < 2:
                return CoordinatorResult(
                    reply_text="There are fewer than two clusters to merge.",
                    cluster_snapshot_id=current_cluster_snapshot_id,
                )
            ids_to_merge = [c.id for c in clusters[:2]]
            new_cluster_snapshot_id = await apply_merge(
                cluster_ids=ids_to_merge,
                parent_cluster_snapshot_id=current_cluster_snapshot_id,
                conversation_id=conversation_id,
                merged_label=intent.merged_label or "Merged",
                accumulated_cost=accumulated_cost,
            )
            reply = "Merged the selected clusters into one."
            return CoordinatorResult(reply_text=reply, cluster_snapshot_id=new_cluster_snapshot_id)

        if intent.mode == NavigationMode.RECUT:
            all_movie_ids = list({mid for c in clusters for m in [] for mid in []})
            if not all_movie_ids:
                all_movie_ids = list_movie_ids()
            concept = None
            if intent.concept:
                concept = await build_concept(intent.concept, conversation_id, message_id, accumulated_cost)
            new_cluster_snapshot_id = await apply_recut(
                movie_ids=all_movie_ids,
                parent_cluster_snapshot_id=current_cluster_snapshot_id,
                conversation_id=conversation_id,
                concept=concept,
                accumulated_cost=accumulated_cost,
            )
            new_cswc = get_cluster_snapshot_with_clusters(new_cluster_snapshot_id)
            n_new = len(new_cswc.clusters) if new_cswc else 0
            reply = f"Re-clustered the catalogue into {n_new} new clusters."
            return CoordinatorResult(reply_text=reply, cluster_snapshot_id=new_cluster_snapshot_id)

        reply = (
            "I understood your request but couldn't perform that operation on the current cluster snapshot. "
            "Try asking to split, merge, or explain a cluster."
        )
        return CoordinatorResult(reply_text=reply, cluster_snapshot_id=current_cluster_snapshot_id or _sentinel_cluster_snapshot_id())

    async def _handle_reset(
        self,
        conversation_id: uuid.UUID,
        conversation_row: ConversationRow,
    ) -> CoordinatorResult:
        """Return to the root (base) cluster snapshot for this conversation.

        Args:
            conversation_id:   Conversation UUID.
            conversation_row:  Current conversation state.

        Returns:
            ``CoordinatorResult`` pointing at the root cluster snapshot.
        """
        root = get_root_cluster_snapshot()
        if root is None:
            return CoordinatorResult(
                reply_text="No base cluster snapshot found yet. Ingest the catalogue first.",
                cluster_snapshot_id=_sentinel_cluster_snapshot_id(),
            )
        set_current_cluster_snapshot(conversation_id, root.id)
        record_conversation_snapshot_ref(conversation_id, root.id)
        cswc = get_cluster_snapshot_with_clusters(root.id)
        n = len(cswc.clusters) if cswc else 0
        return CoordinatorResult(
            reply_text=f"Reset to the base clustering with {n} clusters.",
            cluster_snapshot_id=root.id,
        )

    async def _handle_explain(
        self,
        intent,
        clusters,
        current_cluster_snapshot_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        accumulated_cost: float,
    ) -> CoordinatorResult:
        """Handle an EXPLAIN intent by finding the movie and calling the explanation agent.

        Args:
            intent:                      Classified intent.
            clusters:                    Current cluster list.
            current_cluster_snapshot_id: Active cluster snapshot UUID.
            conversation_id:             Conversation UUID.
            message_id:                  Message UUID.
            accumulated_cost:            Running LLM cost.

        Returns:
            ``CoordinatorResult`` with the explanation text.
        """
        target_cluster = (
            next((c for c in clusters if c.id == intent.target_cluster_id), None)
            if intent.target_cluster_id else (clusters[0] if clusters else None)
        )
        if target_cluster is None or not target_cluster.exemplar_movie_ids:
            return CoordinatorResult(
                reply_text="I couldn't identify which movie or cluster to explain. Please be more specific.",
                cluster_snapshot_id=current_cluster_snapshot_id,
            )

        movie_id = target_cluster.exemplar_movie_ids[0]
        result = await explain_placement(
            movie_id=movie_id,
            cluster_id=target_cluster.id,
            cluster_snapshot_id=current_cluster_snapshot_id,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
        )
        return CoordinatorResult(reply_text=result.text, cluster_snapshot_id=current_cluster_snapshot_id)


async def _label_unlabeled_clusters(
    clusters: list[ClusterRow],
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
) -> list[ClusterRow]:
    """Generate and persist labels for any cluster whose label is None.

    Root clusters arrive from ingest without labels; this function labels them
    lazily on first conversation access.

    Args:
        clusters:         Current cluster list (may contain None-labeled entries).
        conversation_id:  Conversation UUID for LLM logging.
        message_id:       Current message UUID for LLM logging.
        accumulated_cost: Running LLM cost this conversation.

    Returns:
        Cluster list with all None labels replaced by generated ones.
    """
    labeled: list[ClusterRow] = []
    for cluster in clusters:
        if cluster.label is not None:
            labeled.append(cluster)
            continue
        result = await label_cluster(
            exemplar_movie_ids=cluster.exemplar_movie_ids,
            conversation_id=str(conversation_id),
            accumulated_cost=accumulated_cost,
            message_id=str(message_id),
        )
        update_cluster_label(cluster.id, result.label, result.summary)
        log.info(
            "root_cluster_labeled",
            extra={"cluster_id": str(cluster.id), "label": result.label},
        )
        labeled.append(replace(cluster, label=result.label, summary=result.summary))
    return labeled


def _sentinel_cluster_snapshot_id() -> uuid.UUID:
    """Return a zero UUID as a sentinel when no cluster snapshot exists yet."""
    return uuid.UUID("00000000-0000-0000-0000-000000000000")


