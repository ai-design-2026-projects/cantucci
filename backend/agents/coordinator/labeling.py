"""Lazy cluster labeling for the Coordinator.

Root clusters arrive from ingest without labels.  This module labels them on
first conversation access using a single batched LLM call and persists the
results to the database.
"""

import logging
import uuid
from dataclasses import replace

from backend.agents.labeling.agent import label_clusters
from backend.data_access.cluster_snapshots.queries import update_cluster_label
from backend.data_access.cluster_snapshots.types import ClusterRow

log = logging.getLogger(__name__)


async def label_unlabeled_clusters(
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
