import logging
import uuid

from backend.agents.clustering.types import ClusterSnapshotDraft
from backend.agents.labeling.agent import label_clusters
from backend.agents.labeling.types import ClusterLabelContext
from backend.data_access.cluster_snapshots.queries import (
    canonicalize_params,
    create_cluster,
    create_cluster_snapshot,
    create_memberships,
    find_cached_snapshot,
    get_cluster_labels,
    record_conversation_snapshot_ref,
)
from backend.data_access.conversations.queries import set_current_cluster_snapshot
from backend.data_access.movies.queries import fetch_cluster_profile
from backend.settings import get_config_hash

log = logging.getLogger(__name__)


def build_label_contexts(
    draft: ClusterSnapshotDraft,
    cluster_indices: list[int],
) -> list[ClusterLabelContext] | None:
    """Build per-cluster labelling context for operation-produced clusters.

    When the draft carries a concept (e.g. ``drill_down`` by "film length"),
    each context includes that concept, the parent cluster's label as a
    breadcrumb, and aggregate metadata statistics over the cluster's full
    membership so the LLM can name clusters by dimension rather than theme.

    When no concept is present (e.g. a ``merge`` or full-catalogue ``drill_down`` without
    a concept), returns ``None`` so the labeller falls back to title-only behaviour.

    Args:
        draft:           Snapshot draft produced by the most recent operation.
        cluster_indices: Indices into ``draft.clusters`` of the unlabeled entries
                         that need labels.

    Returns:
        List of ``ClusterLabelContext`` in the same order as *cluster_indices*,
        or ``None`` if no concept is available.
    """
    concept: str | None = draft.params.get("concept")
    if not concept:
        return None

    parent_ids = [
        draft.clusters[i].parent_cluster_id
        for i in cluster_indices
        if draft.clusters[i].parent_cluster_id is not None
    ]
    parent_label_map = get_cluster_labels(parent_ids) if parent_ids else {}

    contexts: list[ClusterLabelContext] = []
    for i in cluster_indices:
        cd = draft.clusters[i]
        member_ids = [mid for mid, _ in cd.memberships]
        profile = fetch_cluster_profile(member_ids)
        parent_label = parent_label_map.get(cd.parent_cluster_id) if cd.parent_cluster_id else None
        contexts.append(ClusterLabelContext(
            concept=concept,
            parent_label=parent_label,
            profile=profile,
            pre_set_label=cd.label,
        ))

    return contexts


async def persist_and_label(
    draft: ClusterSnapshotDraft,
    conversation_id: uuid.UUID,
    parent_cluster_snapshot_id: uuid.UUID | None,
    accumulated_cost: float,
) -> tuple[uuid.UUID, float]:
    """Persist a ClusterSnapshotDraft, generate LLM labels in one batch call, and update
    the conversation pointer.

    Looks up an existing snapshot with the same
    ``(parent, operation, canonical params, config_hash)`` first. On a hit,
    record the conversation reference and reuse the cached snapshot without
    re-running the labeler. On a miss, build the snapshot, fire labels in a
    single batched LLM call, and record the reference.

    Args:
        draft:                       The cluster snapshot to persist.
        conversation_id:             Conversation to update.
        parent_cluster_snapshot_id:  Parent cluster snapshot UUID, or ``None`` when
                                     operating from the unclustered state.
        accumulated_cost:            Running LLM cost this conversation.

    Returns:
        Tuple of (cluster snapshot UUID, labeling cost in USD).
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
        return cached, 0.0

    cluster_snapshot_id = create_cluster_snapshot(
        operation=draft.operation,
        params=canon_params,
        config_hash=config_hash,
        parent_id=parent_cluster_snapshot_id,
    )

    unlabeled_indices = [
        i for i, cd in enumerate(draft.clusters)
        if cd.summary is None
    ]

    batch_result = None
    if unlabeled_indices:
        exemplar_groups = [draft.clusters[i].exemplar_movie_ids for i in unlabeled_indices]
        contexts = build_label_contexts(draft, unlabeled_indices)
        batch_result = await label_clusters(
            exemplar_groups=exemplar_groups,
            conversation_id=str(conversation_id),
            accumulated_cost=accumulated_cost,
            contexts=contexts,
        )

    label_map: dict[int, tuple[str, str | None]] = {}
    if batch_result is not None:
        for idx, i in enumerate(unlabeled_indices):
            lr = batch_result.results[idx]
            cd = draft.clusters[i]
            final_label = cd.label if cd.label is not None else lr.label
            label_map[i] = (final_label, lr.summary)

    for i, cluster_draft in enumerate(draft.clusters):
        label, summary = label_map.get(i, (cluster_draft.label, cluster_draft.summary))

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
    label_cost = batch_result.cost if batch_result is not None else 0.0
    log.info(
        "cluster_snapshot_persisted",
        extra={
            "conversation_id": str(conversation_id),
            "cluster_snapshot_id": str(cluster_snapshot_id),
            "operation": draft.operation,
            "n_clusters": len(draft.clusters),
        },
    )
    return cluster_snapshot_id, label_cost
