from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from backend.coordinator.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.intent.types import Modality
from backend.data_access.movies.queries import (
    fetch_modality_embeddings,
    fetch_text_embeddings,
)
from backend.settings import get_settings

if TYPE_CHECKING:
    from backend.agents.concept.types import LinearAxisRep

log = logging.getLogger(__name__)


def build_concept_clusters(
    concept_name: str,
    concept_space: str | None,
    scores: dict[int, float],
    available_ids: list[int],
    parent_cluster_ref: uuid.UUID | None,
    source_cluster_id: uuid.UUID | None,
    parent_cluster_snapshot_id: uuid.UUID | None,
    embedding_spaces: list[Modality],
    target_n_clusters: int | None,
) -> ClusterSnapshotDraft:
    """Build a ``ClusterSnapshotDraft`` by running 1-D HDBSCAN on pre-computed concept scores.

    Separates the clustering logic from embedding/scoring so the reuse branch can
    call this directly with scores already loaded from the database.

    Args:
        concept_name:               Human-readable concept name for params and logging.
        concept_space:              ``"semantic"`` or ``"visual"``; recorded in params. Pass ``None`` when reusing persisted scores.
        scores:                     Dict mapping movie_id → concept score.
        available_ids:              Ordered list of movie IDs (must be keys of ``scores``).
        parent_cluster_ref:         ``parent_cluster_id`` for each ``ClusterDraft``.
        source_cluster_id:          Original source cluster for params recording.
        parent_cluster_snapshot_id: Parent snapshot UUID for params recording.
        embedding_spaces:           Modalities used; recorded in params.
        target_n_clusters:          Optional exact cluster count; ``None`` for emergent HDBSCAN.

    Returns:
        ``ClusterSnapshotDraft`` ready to be persisted.
    """
    import numpy as np

    from backend.coordinator.commands.helpers.clustering import exemplars
    from core.clustering import hdbscan_soft

    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars

    score_values = np.array(
        [scores[mid] for mid in available_ids], dtype=np.float64
    ).reshape(-1, 1)

    min_cs = max(2, min(cfg.clustering.online.min_cluster_size, len(available_ids) // 5))
    min_samp = max(1, min_cs // 3)

    # Cluster on the 1D concept score axis directly — no UMAP (meaningless on 1D)
    result = hdbscan_soft(
        score_values,
        min_cluster_size=min_cs,
        min_samples=min_samp,
        cluster_selection_epsilon=cfg.clustering.online.cluster_selection_epsilon,
        metric="euclidean",
        target_n_clusters=target_n_clusters,
    )

    clusters: list[ClusterDraft] = []
    for ci in range(result.n_clusters):
        col = result.probabilities[:, ci]
        members = [
            (available_ids[i], float(col[i]))
            for i in range(len(available_ids)) if col[i] > 0
        ]
        mids = [m[0] for m in members]
        prbs = [m[1] for m in members]
        total_prob = sum(prbs)
        weighted_score = (
            sum(scores[mid] * prob for mid, prob in zip(mids, prbs)) / total_prob
            if total_prob > 0 else 0.0
        )
        clusters.append(ClusterDraft(
            label=None,
            summary=None,
            exemplar_movie_ids=exemplars(mids, prbs, top_n),
            parent_cluster_id=parent_cluster_ref,
            memberships=members,
            concept_score=round(weighted_score, 4),
        ))

    params: dict = {
        "operation": "cluster",
        "source_cluster_id": str(source_cluster_id) if source_cluster_id else None,
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id) if parent_cluster_snapshot_id else None,
        "concept": concept_name,
        "concept_space": concept_space,
        "embedding_spaces": [s.value for s in embedding_spaces],
        "target_n_clusters": target_n_clusters,
        "n_clusters": len(clusters),
    }
    log.info(
        "concept_cluster_complete",
        extra={
            "source_cluster_id": str(source_cluster_id) if source_cluster_id else None,
            "concept": concept_name,
            "n_clusters": len(clusters),
        },
    )
    return ClusterSnapshotDraft(operation="cluster", params=params, clusters=clusters)


async def concept_cluster(
    source_cluster_id: uuid.UUID | None,
    concept: LinearAxisRep,
    parent_cluster_snapshot_id: uuid.UUID | None,
    embedding_spaces: list[Modality] | None = None,
    movie_ids: list[int] | None = None,
    target_n_clusters: int | None = None,
) -> ClusterSnapshotDraft:
    """Cluster a movie set guided by a semantic concept using 1D density clustering.

    Scores all available movies against the concept, then runs HDBSCAN on the
    1D concept score axis to find natural density clusters. No forced binary
    split is applied — cluster boundaries emerge from the distribution of scores.

    The embedding column used for scoring is determined by ``concept.space``:
    - ``"semantic"`` → ``text_embedding`` (BGE space).
    - ``"visual"`` → ``trailer_embedding`` (CLIP space); movies lacking a CLIP
      embedding are excluded from this clustering.

    The input movie set is resolved in this order:
    1. ``source_cluster_id`` → members of that cluster.
    2. ``movie_ids`` → explicit list (used by cross_filter for pre-filtered sets).
    3. ``parent_cluster_snapshot_id`` → union across that snapshot's clusters.
    4. Otherwise → full catalogue.

    Args:
        source_cluster_id:          Cluster to split; ``None`` to operate on a broader set.
        concept:                    Concept axis that guides the clustering.
        parent_cluster_snapshot_id: Snapshot the source cluster belongs to.
        embedding_spaces:           Modalities for free clustering; unused by the concept
                                    path (embedding space is derived from ``concept.space``).
        movie_ids:                  Explicit movie ID list; used when ``source_cluster_id`` is ``None``.
        target_n_clusters:          Optional exact cluster count requested by the Oracle.
                                    When set, HDBSCAN output is merged or expanded to reach
                                    this count.  ``None`` preserves the emergent count.

    Returns:
        ``ClusterSnapshotDraft`` ready to be persisted.

    Raises:
        ValueError: If no movies or embeddings are found.
    """
    from backend.agents.concept.scoring import score_movies
    from backend.coordinator.commands.helpers.movies import resolve_movie_ids

    if embedding_spaces is None:
        embedding_spaces = [Modality.TEXT]

    resolved_movie_ids = resolve_movie_ids(source_cluster_id, movie_ids, parent_cluster_snapshot_id)
    if not resolved_movie_ids:
        raise ValueError("No movies found for clustering")
    parent_cluster_ref: uuid.UUID | None = source_cluster_id

    if concept.space == "visual":
        modal_data = fetch_modality_embeddings(resolved_movie_ids, ["trailer"])
        emb_map: dict = {mid: v.tolist() for mid, v in modal_data["trailer"].items()}
    else:
        emb_map = fetch_text_embeddings(resolved_movie_ids)

    available_ids = [mid for mid in resolved_movie_ids if mid in emb_map]
    if not available_ids:
        src = str(source_cluster_id) if source_cluster_id else "full catalogue"
        raise ValueError(f"No embeddings found for {src}")

    concept_scores = score_movies(concept, available_ids, emb_map)
    if not concept_scores:
        src = str(source_cluster_id) if source_cluster_id else "full catalogue"
        raise ValueError(f"No concept scores found for {src}")

    return build_concept_clusters(
        concept_name=concept.concept_name,
        concept_space=concept.space,
        scores=concept_scores,
        available_ids=available_ids,
        parent_cluster_ref=parent_cluster_ref,
        source_cluster_id=source_cluster_id,
        parent_cluster_snapshot_id=parent_cluster_snapshot_id,
        embedding_spaces=embedding_spaces,
        target_n_clusters=target_n_clusters,
    )


async def free_cluster(
    source_cluster_id: uuid.UUID | None,
    parent_cluster_snapshot_id: uuid.UUID | None,
    embedding_spaces: list[Modality] | None = None,
    movie_ids: list[int] | None = None,
    target_n_clusters: int | None = None,
) -> ClusterSnapshotDraft:
    """Cluster a movie set without concept guidance.

    Runs HDBSCAN directly on the full resolved input set. Cluster labels
    are generic placeholders; the labeling agent assigns semantic names
    after persistence.

    The input movie set is resolved in this order:
    1. ``source_cluster_id`` → members of that cluster.
    2. ``movie_ids`` → explicit list (used by cross_filter for pre-filtered sets).
    3. ``parent_cluster_snapshot_id`` → union across that snapshot's clusters.
    4. Otherwise → full catalogue.

    Args:
        source_cluster_id:          Cluster to split; ``None`` to operate on a broader set.
        parent_cluster_snapshot_id: Snapshot the source cluster belongs to.
        embedding_spaces:           Modalities to fuse. Defaults to ``[Modality.TEXT]``.
        movie_ids:                  Explicit movie ID list; used when ``source_cluster_id`` is ``None``.
        target_n_clusters:          Optional exact cluster count requested by the Oracle.
                                    When set, HDBSCAN output is merged or expanded to reach
                                    this count.  ``None`` preserves the emergent count.

    Returns:
        ``ClusterSnapshotDraft`` ready to be persisted.

    Raises:
        ValueError: If no movies or embeddings are found.
    """
    from backend.coordinator.commands.helpers.clustering import cluster_group, exemplars, load_embeddings
    from backend.coordinator.commands.helpers.movies import resolve_movie_ids

    if embedding_spaces is None:
        embedding_spaces = [Modality.TEXT]

    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars

    resolved_movie_ids = resolve_movie_ids(source_cluster_id, movie_ids, parent_cluster_snapshot_id)
    if not resolved_movie_ids:
        raise ValueError("No movies found for clustering")
    parent_cluster_ref: uuid.UUID | None = source_cluster_id

    emb_ctx = load_embeddings(resolved_movie_ids, embedding_spaces)
    if not emb_ctx.available_ids:
        src = str(source_cluster_id) if source_cluster_id else "full catalogue"
        raise ValueError(f"No embeddings found for {src}")

    result = cluster_group(emb_ctx.available_ids, emb_ctx, target_n_clusters=target_n_clusters)
    clusters: list[ClusterDraft] = []
    for ci in range(result.n_clusters):
        col = result.probabilities[:, ci]
        members = [(emb_ctx.available_ids[i], float(col[i])) for i in range(len(emb_ctx.available_ids)) if col[i] > 0]
        mids = [m[0] for m in members]
        prbs = [m[1] for m in members]
        clusters.append(ClusterDraft(
            label=None,
            summary=None,
            exemplar_movie_ids=exemplars(mids, prbs, top_n),
            parent_cluster_id=parent_cluster_ref,
            memberships=members,
        ))

    params: dict = {
        "operation": "cluster",
        "source_cluster_id": str(source_cluster_id) if source_cluster_id else None,
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id) if parent_cluster_snapshot_id else None,
        "concept": None,
        "embedding_spaces": [s.value for s in embedding_spaces],
        "target_n_clusters": target_n_clusters,
        "n_clusters": len(clusters),
    }
    log.info(
        "free_cluster_complete",
        extra={
            "source_cluster_id": str(source_cluster_id) if source_cluster_id else None,
            "n_clusters": len(clusters),
        },
    )
    return ClusterSnapshotDraft(operation="cluster", params=params, clusters=clusters)
