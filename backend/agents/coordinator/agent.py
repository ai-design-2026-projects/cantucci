import logging
import uuid
from dataclasses import replace

from backend.agents.clarifier.agent import clarify
from backend.agents.clustering.agent import apply_drill_down, apply_merge, apply_recut
from backend.agents.concept.agent import build_concept
from backend.agents.coordinator.types import CoordinatorResult
from backend.agents.explanation.agent import explain_placement
from backend.agents.intent.agent import classify as classify_intent
from backend.agents.intent.types import Modality, NavigationMode
from backend.agents.labeling.agent import label_clusters
from backend.agents.suggester.agent import suggest
from backend.agents.suggester.signals import (
    compute_cluster_centroids,
    find_dominant_cluster,
    find_noise_fraction,
    find_similar_pairs,
)
from backend.agents.suggester.types import SuggestionResult
from backend.data_access.cluster_snapshots.queries import (
    get_cluster_snapshot_with_clusters,
    get_memberships,
    get_root_cluster_snapshot,
    record_conversation_snapshot_ref,
    update_cluster_label,
)
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.data_access.conversations.queries import set_current_cluster_snapshot
from backend.data_access.conversations.types import ConversationRow
from backend.data_access.movies.queries import fetch_text_embeddings, list_movie_ids
from backend.settings import get_settings

log = logging.getLogger(__name__)

_STATE_CHANGING = {
    NavigationMode.DRILL_DOWN,
    NavigationMode.MERGE,
    NavigationMode.RECUT,
    NavigationMode.RESET,
}


class Coordinator:
    """
    Orchestrates one user message through the agent pipeline.
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
          2. Label any unlabeled clusters (single batched LLM call).
          3. Classify intent (Intent agent).
          4. If confidence is below threshold for a state-changing mode, call the
             Clarifier agent and return a disambiguation question without modifying state.
          5. Branch on mode: concept → cluster op → persist, or explain, or direct reply.
          6. After state-changing ops, run the Suggester agent on the resulting snapshot.
          7. Return reply, updated snapshot id, and optional suggestion.

        Args:
            conversation_id:   Conversation UUID.
            user_message:      Raw user message text.
            conversation_row:  Pre-loaded conversation row (avoids double DB hit).

        Returns:
            ``CoordinatorResult`` with reply text, active cluster snapshot ID, and
            optional follow-up suggestion.
        """
        current_cluster_snapshot_id = conversation_row.current_cluster_snapshot_id
        accumulated_cost = 0.0

        current_snapshot = get_cluster_snapshot_with_clusters(current_cluster_snapshot_id) if current_cluster_snapshot_id else None
        current_clusters = current_snapshot.clusters if current_snapshot else []

        message_id = uuid.uuid4()

        clusters = current_clusters
        if any(cluster.label is None for cluster in current_clusters):
            clusters, label_cost = await _label_unlabeled_clusters(
                current_clusters, conversation_id, message_id, accumulated_cost
            )
            accumulated_cost += label_cost

        intent = await classify_intent(
            user_message=user_message,
            clusters=clusters,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
        )
        accumulated_cost += intent.cost

        cfg = get_settings()
        if (
            intent.confidence < cfg.intent.confidence_threshold
            and intent.navigationMode in _STATE_CHANGING
        ):
            log.info(
                "coordinator_low_confidence_gate",
                extra={
                    "conversation_id": str(conversation_id),
                    "navigation_mode": intent.navigationMode.value,
                    "confidence": intent.confidence,
                    "threshold": cfg.intent.confidence_threshold,
                    "concept": intent.concept,
                },
            )
            clarification = await clarify(
                user_message=user_message,
                clusters=clusters,
                intent=intent,
                conversation_id=conversation_id,
                message_id=message_id,
                accumulated_cost=accumulated_cost,
            )
            accumulated_cost += clarification.cost
            return CoordinatorResult(
                reply_text=clarification.text,
                cluster_snapshot_id=current_cluster_snapshot_id or _sentinel_cluster_snapshot_id(),
            )

        log.info(
            "coordinator_dispatch",
            extra={
                "conversation_id": str(conversation_id),
                "intent_mode": intent.navigationMode.value,
                "n_clusters": len(clusters),
            },
        )

        if intent.navigationMode == NavigationMode.SMALL_TALK:
            reply = (
                "I'm here to help you explore the movie catalogue through clustering. "
                "You can ask me to split a cluster, merge groups, or explain a placement."
            )
            cluster_snapshot_id = current_cluster_snapshot_id or _sentinel_cluster_snapshot_id()
            return CoordinatorResult(reply_text=reply, cluster_snapshot_id=cluster_snapshot_id)

        if intent.navigationMode == NavigationMode.RESET or current_cluster_snapshot_id is None:
            return await self._handle_reset(conversation_id, conversation_row)

        if intent.navigationMode == NavigationMode.EXPLAIN:
            return await self._handle_explain(
                intent, clusters, current_cluster_snapshot_id, conversation_id, message_id, accumulated_cost
            )

        if intent.navigationMode == NavigationMode.DRILL_DOWN:
            target_id = intent.target_cluster_id or (clusters[0].id if clusters else None)
            if target_id is None:
                return CoordinatorResult(
                    reply_text="Please specify which cluster to split.",
                    cluster_snapshot_id=current_cluster_snapshot_id,
                )
            concept = None
            if intent.concept:
                concept = await build_concept(intent.concept, conversation_id, message_id, accumulated_cost)
                accumulated_cost += concept.cost
            new_cluster_snapshot_id = await apply_drill_down(
                source_cluster_id=target_id,
                parent_cluster_snapshot_id=current_cluster_snapshot_id,
                conversation_id=conversation_id,
                concept=concept,
                accumulated_cost=accumulated_cost,
                embedding_spaces=intent.embedding_spaces,
            )
            new_cswc = get_cluster_snapshot_with_clusters(new_cluster_snapshot_id)
            n_new = len(new_cswc.clusters) if new_cswc else 0
            labels = [c.label for c in (new_cswc.clusters if new_cswc else [])]
            reply = f"Split into {n_new} sub-clusters: {', '.join(labels[:5])}{'…' if n_new > 5 else ''}."
            suggestion = await _maybe_suggest(
                new_cluster_snapshot_id=new_cluster_snapshot_id,
                new_clusters=new_cswc.clusters if new_cswc else [],
                last_operation=reply,
                conversation_id=conversation_id,
                message_id=message_id,
                accumulated_cost=accumulated_cost,
            )
            accumulated_cost += suggestion.cost if suggestion else 0.0
            return CoordinatorResult(
                reply_text=reply,
                cluster_snapshot_id=new_cluster_snapshot_id,
                suggestion=suggestion.text if suggestion else None,
            )

        if intent.navigationMode == NavigationMode.MERGE:
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
            new_cswc = get_cluster_snapshot_with_clusters(new_cluster_snapshot_id)
            suggestion = await _maybe_suggest(
                new_cluster_snapshot_id=new_cluster_snapshot_id,
                new_clusters=new_cswc.clusters if new_cswc else [],
                last_operation=reply,
                conversation_id=conversation_id,
                message_id=message_id,
                accumulated_cost=accumulated_cost,
            )
            accumulated_cost += suggestion.cost if suggestion else 0.0
            return CoordinatorResult(
                reply_text=reply,
                cluster_snapshot_id=new_cluster_snapshot_id,
                suggestion=suggestion.text if suggestion else None,
            )

        if intent.navigationMode == NavigationMode.RECUT:
            all_movie_ids = list_movie_ids()
            concept = None
            if intent.concept:
                concept = await build_concept(intent.concept, conversation_id, message_id, accumulated_cost)
                accumulated_cost += concept.cost
            new_cluster_snapshot_id = await apply_recut(
                movie_ids=all_movie_ids,
                parent_cluster_snapshot_id=current_cluster_snapshot_id,
                conversation_id=conversation_id,
                concept=concept,
                accumulated_cost=accumulated_cost,
                embedding_spaces=intent.embedding_spaces,
            )
            new_cswc = get_cluster_snapshot_with_clusters(new_cluster_snapshot_id)
            n_new = len(new_cswc.clusters) if new_cswc else 0
            reply = f"Re-clustered the catalogue into {n_new} new clusters."
            suggestion = await _maybe_suggest(
                new_cluster_snapshot_id=new_cluster_snapshot_id,
                new_clusters=new_cswc.clusters if new_cswc else [],
                last_operation=reply,
                conversation_id=conversation_id,
                message_id=message_id,
                accumulated_cost=accumulated_cost,
            )
            accumulated_cost += suggestion.cost if suggestion else 0.0
            return CoordinatorResult(
                reply_text=reply,
                cluster_snapshot_id=new_cluster_snapshot_id,
                suggestion=suggestion.text if suggestion else None,
            )

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
) -> tuple[list[ClusterRow], float]:
    """Generate and persist labels for any cluster whose label is None.

    Root clusters arrive from ingest without labels; this function labels them
    lazily on first conversation access using a single batched LLM call.

    Args:
        clusters:         Current cluster list (may contain None-labeled entries).
        conversation_id:  Conversation UUID for LLM logging.
        message_id:       Current message UUID for LLM logging.
        accumulated_cost: Running LLM cost this conversation.

    Returns:
        Tuple of (cluster list with all None labels replaced, total labeling cost).
    """
    unlabeled = [c for c in clusters if c.label is None]
    if not unlabeled:
        return clusters, 0.0

    exemplar_groups = [c.exemplar_movie_ids for c in unlabeled]
    batch_result = await label_clusters(
        exemplar_groups=exemplar_groups,
        conversation_id=str(conversation_id),
        accumulated_cost=accumulated_cost,
        message_id=str(message_id),
    )

    label_by_id: dict[uuid.UUID, tuple[str, str | None]] = {}
    for i, cluster in enumerate(unlabeled):
        lr = batch_result.results[i]
        update_cluster_label(cluster.id, lr.label, lr.summary)
        label_by_id[cluster.id] = (lr.label, lr.summary)
        log.info("root_cluster_labeled", extra={"cluster_id": str(cluster.id), "label": lr.label})

    labeled = [
        replace(c, label=label_by_id[c.id][0], summary=label_by_id[c.id][1])
        if c.id in label_by_id else c
        for c in clusters
    ]
    return labeled, batch_result.cost


async def _maybe_suggest(
    new_cluster_snapshot_id: uuid.UUID,
    new_clusters: list[ClusterRow],
    last_operation: str,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
) -> SuggestionResult | None:
    """Compute deterministic signals from the new snapshot and optionally call the suggester.

    Returns None immediately when suggestions are disabled or no signal exceeds its
    threshold, avoiding any LLM call in those cases.

    Args:
        new_cluster_snapshot_id: UUID of the freshly created cluster snapshot.
        new_clusters:            Cluster list of the new snapshot.
        last_operation:          Human-readable summary of the operation just completed.
        conversation_id:         Conversation UUID for logging.
        message_id:              Current message UUID for logging.
        accumulated_cost:        Running LLM cost this conversation.

    Returns:
        ``SuggestionResult`` if the LLM was called, or None if suggestions were skipped.
    """
    cfg = get_settings()
    if not cfg.suggestions.enabled:
        return None
    if not new_clusters:
        return None

    all_exemplar_ids = list({
        mid
        for cluster in new_clusters
        for mid in cluster.exemplar_movie_ids
    })
    emb_map = fetch_text_embeddings(all_exemplar_ids)

    centroids = compute_cluster_centroids(new_clusters, emb_map)

    signals: list[str] = []

    similar_pairs = find_similar_pairs(centroids, distance_max=cfg.suggestions.similar_pair_distance_max)
    id_to_label = {c.id: (c.label or "Unlabeled") for c in new_clusters}
    for a_id, b_id, dist in similar_pairs:
        label_a = id_to_label.get(a_id, str(a_id))
        label_b = id_to_label.get(b_id, str(b_id))
        signals.append(
            f"similar_pair: clusters '{label_a}' and '{label_b}' are very similar "
            f"(cosine distance {dist:.2f})"
        )
        if len(signals) >= cfg.suggestions.top_n_signals:
            break

    if len(signals) < cfg.suggestions.top_n_signals:
        memberships_by_cluster = {
            c.id: get_memberships(c.id) for c in new_clusters
        }

        dominant_id = find_dominant_cluster(
            memberships_by_cluster, dominance_fraction=cfg.suggestions.dominance_fraction
        )
        if dominant_id is not None:
            label = id_to_label.get(dominant_id, str(dominant_id))
            total = sum(len(rows) for rows in memberships_by_cluster.values())
            count = len(memberships_by_cluster[dominant_id])
            signals.append(
                f"dominant_cluster: '{label}' holds {count}/{total} members "
                f"({100 * count / total:.0f}%) — consider splitting it further"
            )

        if len(signals) < cfg.suggestions.top_n_signals:
            noise_frac = find_noise_fraction(memberships_by_cluster, n_clusters=len(new_clusters))
            if noise_frac >= cfg.suggestions.noise_fraction_floor:
                signals.append(
                    f"high_noise: {100 * noise_frac:.0f}% of memberships look like noise — "
                    "consider re-clustering with a guiding concept"
                )

    if not signals:
        return None

    return await suggest(
        last_operation=last_operation,
        clusters=new_clusters,
        signals=signals[:cfg.suggestions.top_n_signals],
        conversation_id=conversation_id,
        message_id=message_id,
        accumulated_cost=accumulated_cost,
    )


def _sentinel_cluster_snapshot_id() -> uuid.UUID:
    """Return a zero UUID as a sentinel when no cluster snapshot exists yet."""
    return uuid.UUID("00000000-0000-0000-0000-000000000000")
