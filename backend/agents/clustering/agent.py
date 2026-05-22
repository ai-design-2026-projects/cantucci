import logging
import uuid

from backend.agents.clustering.operations.drill_down import drill_down
from backend.agents.clustering.operations.merge import merge_clusters
from backend.agents.clustering.operations.recut import recut
from backend.agents.clustering.types import ClusterSnapshotDraft
from backend.agents.concept.types import ConceptRep
from backend.agents.labeling.agent import label_cluster
from backend.data_access.cluster_snapshots.queries import (
    canonicalize_params,
    create_cluster,
    create_cluster_snapshot,
    create_memberships,
    find_cached_snapshot,
    record_conversation_snapshot_ref,
)
from backend.data_access.conversations.queries import set_current_cluster_snapshot
from backend.settings import get_config_hash

log = logging.getLogger(__name__)


async def apply_drill_down(
    source_cluster_id: uuid.UUID,
    parent_cluster_snapshot_id: uuid.UUID,
    conversation_id: uuid.UUID,
    concept: ConceptRep | None,
    accumulated_cost: float,
) -> uuid.UUID:
    """Drill down into one cluster and persist the resulting cluster snapshot.

    Args:
        source_cluster_id:           Cluster to split.
        parent_cluster_snapshot_id:  Cluster snapshot the cluster belongs to.
        conversation_id:             Conversation to update the current_cluster_snapshot_id pointer.
        concept:                     Optional concept to guide the split.
        accumulated_cost:            Running LLM cost this conversation.

    Returns:
        UUID of the newly created cluster snapshot.
    """
    draft = await drill_down(source_cluster_id, concept, parent_cluster_snapshot_id)
    return await _persist_and_label(draft, conversation_id, parent_cluster_snapshot_id, accumulated_cost)


async def apply_merge(
    cluster_ids: list[uuid.UUID],
    parent_cluster_snapshot_id: uuid.UUID,
    conversation_id: uuid.UUID,
    merged_label: str,
    accumulated_cost: float,
) -> uuid.UUID:
    """Merge clusters and persist the resulting cluster snapshot.

    Args:
        cluster_ids:                 Clusters to merge.
        parent_cluster_snapshot_id:  Their parent cluster snapshot.
        conversation_id:             Conversation to update.
        merged_label:                Label for the merged cluster.
        accumulated_cost:            Running LLM cost this conversation.

    Returns:
        UUID of the newly created cluster snapshot.
    """
    draft = await merge_clusters(cluster_ids, parent_cluster_snapshot_id, merged_label)
    return await _persist_and_label(draft, conversation_id, parent_cluster_snapshot_id, accumulated_cost)


async def apply_recut(
    movie_ids: list[int],
    parent_cluster_snapshot_id: uuid.UUID,
    conversation_id: uuid.UUID,
    concept: ConceptRep | None,
    accumulated_cost: float,
) -> uuid.UUID:
    """Re-cluster a movie set and persist the result as a new cluster snapshot.

    Args:
        movie_ids:                   Movies to recluster.
        parent_cluster_snapshot_id:  Cluster snapshot being replaced.
        conversation_id:             Conversation to update.
        concept:                     Optional concept.
        accumulated_cost:            Running LLM cost this conversation.

    Returns:
        UUID of the newly created cluster snapshot.
    """
    draft = await recut(movie_ids, parent_cluster_snapshot_id, concept)
    return await _persist_and_label(draft, conversation_id, parent_cluster_snapshot_id, accumulated_cost)


async def _persist_and_label(
    draft: ClusterSnapshotDraft,
    conversation_id: uuid.UUID,
    parent_cluster_snapshot_id: uuid.UUID,
    accumulated_cost: float,
) -> uuid.UUID:
    """Persist a ClusterSnapshotDraft, generate LLM labels, and update the conversation pointer.

    Looks up an existing snapshot with the same
    ``(parent, operation, canonical params, config_hash)`` first. On a hit,
    record the conversation reference and reuse the cached snapshot without
    re-running the labeler. On a miss, build the snapshot, fire labels, and
    record the reference.

    Args:
        draft:                       The cluster snapshot to persist.
        conversation_id:             Conversation to update.
        parent_cluster_snapshot_id:  Parent cluster snapshot UUID.
        accumulated_cost:            Running LLM cost this conversation.

    Returns:
        UUID of the cached-or-newly-created cluster snapshot.
    """
    canon_params = canonicalize_params(draft.params)
    config_hash = get_config_hash()

    cached = find_cached_snapshot(parent_cluster_snapshot_id, draft.operation, canon_params, config_hash)
    if cached is not None:
        record_conversation_snapshot_ref(conversation_id, cached)
        set_current_cluster_snapshot(conversation_id, cached)
        log.info(
            "snapshot_cache_hit",
            extra={
                "conversation_id": str(conversation_id),
                "cluster_snapshot_id": str(cached),
                "operation": draft.operation,
            },
        )
        return cached

    cluster_snapshot_id = create_cluster_snapshot(
        operation=draft.operation,
        params=canon_params,
        config_hash=config_hash,
        parent_id=parent_cluster_snapshot_id,
    )

    for cluster_draft in draft.clusters:
        needs_label = (
            cluster_draft.label is None
            or cluster_draft.label.startswith("Cluster ")
        )
        if needs_label:
            result = await label_cluster(
                exemplar_movie_ids=cluster_draft.exemplar_movie_ids,
                conversation_id=str(conversation_id),
                accumulated_cost=accumulated_cost,
            )
            label, summary = result.label, result.summary
        else:
            label, summary = cluster_draft.label, cluster_draft.summary

        cluster_id = create_cluster(
            cluster_snapshot_id=cluster_snapshot_id,
            label=label,
            summary=summary,
            exemplar_movie_ids=cluster_draft.exemplar_movie_ids,
            parent_cluster_id=cluster_draft.parent_cluster_id,
        )

        memberships: list[tuple[uuid.UUID, int, float]] = [
            (cluster_id, mid, prob) for mid, prob in cluster_draft.memberships
        ]
        create_memberships(memberships)

    record_conversation_snapshot_ref(conversation_id, cluster_snapshot_id)
    set_current_cluster_snapshot(conversation_id, cluster_snapshot_id)
    log.info(
        "cluster_snapshot_persisted",
        extra={
            "conversation_id": str(conversation_id),
            "cluster_snapshot_id": str(cluster_snapshot_id),
            "operation": draft.operation,
            "n_clusters": len(draft.clusters),
        },
    )
    return cluster_snapshot_id
