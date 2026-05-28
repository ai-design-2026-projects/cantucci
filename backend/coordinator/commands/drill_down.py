from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from backend.coordinator.commands._helpers import _persist_draft, resolve_target_or_clarify
from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.coordinator.tools.clarification_state import mark_awaiting
from backend.coordinator.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.intent.types import Modality
from backend.agents.responder import replies
from backend.data_access.movies.queries import fetch_modality_embeddings, fetch_text_embeddings
from backend.settings import get_settings

if TYPE_CHECKING:
    from backend.agents.concept.types import ConceptRep
    from core.clustering import SoftClusterResult

log = logging.getLogger(__name__)

_LABEL_PLACEHOLDER = "Cluster"


@dataclass(frozen=True, slots=True)
class DrillDownCommand:
    """Split a cluster (or the full catalogue) into sub-clusters.

    Attributes:
        target_cluster_id: Cluster to split; None = full set or unclustered state.
        concept:           Optional semantic concept string to guide clustering.
        embedding_spaces:  Modalities to fuse for embedding loading.
        confidence:        LLM confidence [0, 1].
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = False
    CREATES_SNAPSHOT: ClassVar[bool] = True
    READS_CLUSTERS: ClassVar[bool] = True

    target_cluster_id: uuid.UUID | None
    concept: str | None
    embedding_spaces: list[Modality]
    confidence: float

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Split target cluster (or full catalogue) into sub-clusters.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reply, new snapshot id, and cost.
        """
        from backend.agents.concept.agent import agent as concept_agent

        target_id = resolve_target_or_clarify(ctx, self.target_cluster_id)
        if target_id is None and ctx.clusters:
            mark_awaiting(ctx.conversation_id)
            return ActionResult(
                reply_fragment=replies.format_drill_down_clarification([c.label for c in ctx.clusters]),
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        step_cost = 0.0
        concept_rep = None
        if self.concept:
            ctx.reporter.step("concept")
            concept_rep = await concept_agent.run(
                concept_name=self.concept,
                conversation_id=ctx.conversation_id,
                message_id=ctx.message_id,
                accumulated_cost=ctx.accumulated_cost + step_cost,
            )
            step_cost += concept_rep.cost

        ctx.reporter.step("clustering")
        if concept_rep is not None:
            draft = await concept_drill_down(
                source_cluster_id=target_id,
                concept=concept_rep,
                parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                embedding_spaces=self.embedding_spaces,
            )
        else:
            draft = await free_drill_down(
                source_cluster_id=target_id,
                parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                embedding_spaces=self.embedding_spaces,
            )

        new_snapshot_id, persist_cost, n_movies, new_clusters = await _persist_draft(ctx, draft, step_cost)
        labels = [c.label for c in new_clusters]
        return ActionResult(
            reply_fragment=replies.format_drill_down_reply(labels, len(new_clusters), n_movies),
            cluster_snapshot_id=new_snapshot_id,
            step_cost=persist_cost,
        )


@dataclass(frozen=True, slots=True)
class _EmbeddingContext:
    """Resolved embeddings and availability data for a set of movies.

    Attributes:
        available_ids:    Movie IDs that have embeddings in all requested spaces.
        emb_map:          Text embedding map (movie_id → vector); used for concept scoring and single-modal clustering.
        multi_modal:      True when more than one embedding space was requested.
        modal_data:       Per-modality embedding dicts; non-empty only when ``multi_modal`` is True.
        embedding_spaces: The modalities that were loaded.
    """

    available_ids: list[int]
    emb_map: dict
    multi_modal: bool
    modal_data: dict
    embedding_spaces: list[Modality]


def _load_embeddings(resolved_movie_ids: list[int], embedding_spaces: list[Modality]) -> _EmbeddingContext:
    """Fetch embeddings for the resolved movie set and return a bundled context.

    For single-modality TEXT requests only the text embedding map is fetched.
    For multi-modal requests all specified modalities are fetched and movies
    lacking any one modality are excluded.

    Args:
        resolved_movie_ids: Movie IDs whose embeddings should be loaded.
        embedding_spaces:   Modalities to load.

    Returns:
        ``_EmbeddingContext`` with available IDs, emb_map, and raw modal data.

    Raises:
        ValueError: If no embeddings are found for the resolved set.
    """
    if len(embedding_spaces) == 1 and embedding_spaces[0] == Modality.TEXT:
        emb_map = fetch_text_embeddings(resolved_movie_ids)
        available_ids = [mid for mid in resolved_movie_ids if mid in emb_map]
        return _EmbeddingContext(
            available_ids=available_ids,
            emb_map=emb_map,
            multi_modal=False,
            modal_data={},
            embedding_spaces=embedding_spaces,
        )

    space_keys = [s.value for s in embedding_spaces]
    modal_data = fetch_modality_embeddings(resolved_movie_ids, space_keys)
    available_ids = [
        mid for mid in resolved_movie_ids
        if all(mid in modal_data[m] for m in space_keys)
    ]
    emb_map = {mid: modal_data["text"][mid].tolist() for mid in available_ids if "text" in modal_data}
    return _EmbeddingContext(
        available_ids=available_ids,
        emb_map=emb_map,
        multi_modal=True,
        modal_data=modal_data,
        embedding_spaces=embedding_spaces,
    )


def _cluster_group(group_ids: list[int], emb_ctx: _EmbeddingContext) -> SoftClusterResult:
    """Cluster a group of movies using the given embedding context.

    Dispatches to multi-modal (precomputed distance matrix) or single-modal
    (UMAP + HDBSCAN) based on ``emb_ctx.multi_modal``.

    Args:
        group_ids: Movie IDs to cluster (must be a subset of ``emb_ctx.available_ids``).
        emb_ctx:   Embedding context produced by ``_load_embeddings``.

    Returns:
        ``SoftClusterResult`` for the group.
    """
    import numpy as np

    from backend.coordinator.commands._clustering import reduce_for_clustering, subcluster
    from core.fusion import combined_distance_matrix

    cfg = get_settings()
    if emb_ctx.multi_modal:
        embs_by_modality = {
            space.value: np.array(
                [emb_ctx.modal_data[space.value][mid] for mid in group_ids], dtype=np.float32
            )
            for space in emb_ctx.embedding_spaces
        }
        dist_mat = combined_distance_matrix(embs_by_modality, cfg.fusion.runtime_weights)
        return subcluster(
            None,
            cfg.clustering.online.drilldown_min_cluster_size,
            distance_matrix=dist_mat,
            cluster_selection_epsilon=cfg.clustering.online.cluster_selection_epsilon,
        )
    group_embs = np.array([emb_ctx.emb_map[mid] for mid in group_ids], dtype=np.float32)
    group_embs = reduce_for_clustering(group_embs, cfg.umap, cfg.split.seed)
    return subcluster(
        group_embs,
        cfg.clustering.online.drilldown_min_cluster_size,
        cluster_selection_epsilon=cfg.clustering.online.cluster_selection_epsilon,
    )


async def concept_drill_down(
    source_cluster_id: uuid.UUID | None,
    concept: ConceptRep,
    parent_cluster_snapshot_id: uuid.UUID | None,
    embedding_spaces: list[Modality] | None = None,
    movie_ids: list[int] | None = None,
) -> ClusterSnapshotDraft:
    """Cluster a movie set guided by a semantic concept using 1D density clustering.

    Scores all available movies against the concept, then runs HDBSCAN on the
    1D concept score axis to find natural density clusters. No forced binary
    split is applied — cluster boundaries emerge from the distribution of scores.

    The input movie set is resolved in this order:
    1. ``source_cluster_id`` → members of that cluster.
    2. ``movie_ids`` → explicit list (used by cross_filter for pre-filtered sets).
    3. ``parent_cluster_snapshot_id`` → union across that snapshot's clusters.
    4. Otherwise → full catalogue.

    Args:
        source_cluster_id:          Cluster to split; ``None`` to operate on a broader set.
        concept:                    Concept that guides the clustering axis.
        parent_cluster_snapshot_id: Snapshot the source cluster belongs to.
        embedding_spaces:           Modalities to fuse for embedding loading. Defaults to ``[Modality.TEXT]``.
        movie_ids:                  Explicit movie ID list; used when ``source_cluster_id`` is ``None``.

    Returns:
        ``ClusterSnapshotDraft`` ready to be persisted.

    Raises:
        ValueError: If no movies or embeddings are found.
    """
    import numpy as np

    from backend.agents.concept.scoring import score_movies
    from backend.coordinator.commands._clustering import exemplars, resolve_movie_ids
    from core.clustering import hdbscan_soft

    if embedding_spaces is None:
        embedding_spaces = [Modality.TEXT]

    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars

    resolved_movie_ids = resolve_movie_ids(source_cluster_id, movie_ids, parent_cluster_snapshot_id)
    if not resolved_movie_ids:
        raise ValueError("No movies found for clustering")
    parent_cluster_ref: uuid.UUID | None = source_cluster_id

    emb_ctx = _load_embeddings(resolved_movie_ids, embedding_spaces)
    if not emb_ctx.available_ids:
        src = str(source_cluster_id) if source_cluster_id else "full catalogue"
        raise ValueError(f"No embeddings found for {src}")

    concept_scores = score_movies(concept, emb_ctx.available_ids, emb_ctx.emb_map)
    score_values = np.array(
        [concept_scores[mid] for mid in emb_ctx.available_ids], dtype=np.float64
    ).reshape(-1, 1)

    min_cs = max(2, min(cfg.clustering.online.drilldown_min_cluster_size, len(emb_ctx.available_ids) // 5))
    min_samp = max(1, min_cs // 3)

    # Cluster on the 1D concept score axis directly — no UMAP (meaningless on 1D)
    result = hdbscan_soft(
        score_values,
        min_cluster_size=min_cs,
        min_samples=min_samp,
        cluster_selection_epsilon=cfg.clustering.online.cluster_selection_epsilon,
        metric="euclidean",
    )

    clusters: list[ClusterDraft] = []
    for ci in range(result.n_clusters):
        col = result.probabilities[:, ci]
        members = [
            (emb_ctx.available_ids[i], float(col[i]))
            for i in range(len(emb_ctx.available_ids)) if col[i] > 0
        ]
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
        "operation": "drill_down",
        "source_cluster_id": str(source_cluster_id) if source_cluster_id else None,
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id) if parent_cluster_snapshot_id else None,
        "concept": concept.concept_name,
        "embedding_spaces": [s.value for s in embedding_spaces],
        "n_clusters": len(clusters),
    }
    log.info(
        "concept_drill_down_complete",
        extra={
            "source_cluster_id": str(source_cluster_id) if source_cluster_id else None,
            "concept": concept.concept_name,
            "n_clusters": len(clusters),
        },
    )
    return ClusterSnapshotDraft(operation="drill_down", params=params, clusters=clusters)


async def free_drill_down(
    source_cluster_id: uuid.UUID | None,
    parent_cluster_snapshot_id: uuid.UUID | None,
    embedding_spaces: list[Modality] | None = None,
    movie_ids: list[int] | None = None,
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

    Returns:
        ``ClusterSnapshotDraft`` ready to be persisted.

    Raises:
        ValueError: If no movies or embeddings are found.
    """
    from backend.coordinator.commands._clustering import exemplars, resolve_movie_ids

    if embedding_spaces is None:
        embedding_spaces = [Modality.TEXT]

    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars

    resolved_movie_ids = resolve_movie_ids(source_cluster_id, movie_ids, parent_cluster_snapshot_id)
    if not resolved_movie_ids:
        raise ValueError("No movies found for clustering")
    parent_cluster_ref: uuid.UUID | None = source_cluster_id

    emb_ctx = _load_embeddings(resolved_movie_ids, embedding_spaces)
    if not emb_ctx.available_ids:
        src = str(source_cluster_id) if source_cluster_id else "full catalogue"
        raise ValueError(f"No embeddings found for {src}")

    result = _cluster_group(emb_ctx.available_ids, emb_ctx)
    clusters: list[ClusterDraft] = []
    for ci in range(result.n_clusters):
        col = result.probabilities[:, ci]
        members = [(emb_ctx.available_ids[i], float(col[i])) for i in range(len(emb_ctx.available_ids)) if col[i] > 0]
        mids = [m[0] for m in members]
        prbs = [m[1] for m in members]
        clusters.append(ClusterDraft(
            label=f"{_LABEL_PLACEHOLDER} {ci + 1}",
            summary=None,
            exemplar_movie_ids=exemplars(mids, prbs, top_n),
            parent_cluster_id=parent_cluster_ref,
            memberships=members,
        ))

    params: dict = {
        "operation": "drill_down",
        "source_cluster_id": str(source_cluster_id) if source_cluster_id else None,
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id) if parent_cluster_snapshot_id else None,
        "concept": None,
        "embedding_spaces": [s.value for s in embedding_spaces],
        "n_clusters": len(clusters),
    }
    log.info(
        "free_drill_down_complete",
        extra={
            "source_cluster_id": str(source_cluster_id) if source_cluster_id else None,
            "n_clusters": len(clusters),
        },
    )
    return ClusterSnapshotDraft(operation="drill_down", params=params, clusters=clusters)
