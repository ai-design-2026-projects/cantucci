import uuid

from backend.agents.responder.agent import agent as responder_agent
from backend.agents.responder.signals import (
    compute_cluster_centroids,
    find_dominant_cluster,
    find_noise_fraction,
    find_similar_pairs,
)
from backend.agents.responder.types import SuggestionResult
from backend.data_access.cluster_snapshots.queries import get_memberships
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.data_access.movies.queries import fetch_text_embeddings
from backend.settings import get_settings


async def maybe_suggest(
    new_cluster_snapshot_id: uuid.UUID,
    new_clusters: list[ClusterRow],
    last_operation: str,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
) -> SuggestionResult | None:
    """Compute deterministic signals from the new snapshot and optionally call the responder.

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

    memberships_by_cluster = {
        c.id: get_memberships(c.id) for c in new_clusters
    }

    all_member_ids = list({
        row.movie_id
        for rows in memberships_by_cluster.values()
        for row in rows
    })
    emb_map = fetch_text_embeddings(all_member_ids)

    centroids = compute_cluster_centroids(memberships_by_cluster, emb_map)

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

    return await responder_agent.run(
        last_operation=last_operation,
        clusters=new_clusters,
        signals=signals[:cfg.suggestions.top_n_signals],
        conversation_id=conversation_id,
        message_id=message_id,
        accumulated_cost=accumulated_cost,
    )
