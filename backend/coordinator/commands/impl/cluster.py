from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass
from typing import ClassVar

from backend.coordinator.commands._helpers import (
    _NUMERIC_ATTRIBUTES,
    _persist_draft,
    merge_in_siblings,
    resolve_target_or_clarify,
)
from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.coordinator.tools.clarification_state import mark_awaiting
from backend.agents.concept.types import PendingConcept
from backend.coordinator.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.intent.types import Modality, PartitionSpec
from backend.agents.responder import replies
from backend.data_access.movies.queries import (
    fetch_modality_embeddings,
    fetch_numeric_stats,
    fetch_partition_values,
    fetch_text_embeddings,
)
from backend.settings import get_settings
from backend.agents.concept.types import LinearAxisRep
from core.clustering import SoftClusterResult

log = logging.getLogger(__name__)


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


def _cluster_group(
    group_ids: list[int],
    emb_ctx: _EmbeddingContext,
    target_n_clusters: int | None = None,
) -> SoftClusterResult:
    """Cluster a group of movies using the given embedding context.

    Dispatches to multi-modal (precomputed distance matrix) or single-modal
    (UMAP + HDBSCAN) based on ``emb_ctx.multi_modal``.

    Args:
        group_ids:         Movie IDs to cluster (must be a subset of ``emb_ctx.available_ids``).
        emb_ctx:           Embedding context produced by ``_load_embeddings``.
        target_n_clusters: Optional exact cluster count requested by the Oracle.
                           Forwarded to ``subcluster`` / ``hdbscan_soft``.

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
            target_n_clusters=target_n_clusters,
        )
    group_embs = np.array([emb_ctx.emb_map[mid] for mid in group_ids], dtype=np.float32)
    group_embs = reduce_for_clustering(group_embs, cfg.umap, cfg.split.seed)
    return subcluster(
        group_embs,
        cfg.clustering.online.drilldown_min_cluster_size,
        cluster_selection_epsilon=cfg.clustering.online.cluster_selection_epsilon,
        target_n_clusters=target_n_clusters,
    )


def _build_concept_clusters(
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

    from backend.coordinator.commands._clustering import exemplars
    from core.clustering import hdbscan_soft

    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars

    score_values = np.array(
        [scores[mid] for mid in available_ids], dtype=np.float64
    ).reshape(-1, 1)

    min_cs = max(2, min(cfg.clustering.online.drilldown_min_cluster_size, len(available_ids) // 5))
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


async def _concept_cluster(
    source_cluster_id: uuid.UUID | None,
    concept: "LinearAxisRep",
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
    from backend.coordinator.commands._clustering import resolve_movie_ids

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
        raise ValueError(f"No embeddings found for {src}")

    return _build_concept_clusters(
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

async def _free_cluster(
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

    result = _cluster_group(emb_ctx.available_ids, emb_ctx, target_n_clusters=target_n_clusters)
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


@dataclass(frozen=True, slots=True)
class ClusterCommand:
    """Split a cluster (or the full catalogue) into sub-groups.

    Dispatches to one of two branches based on whether a ``partition_spec`` is
    provided:

    * **Deterministic branch** (``partition_spec`` is not ``None``): groups movies by
      an exact metadata attribute (genre, runtime, release_year, director,
      vote_average, original_language) with probability 1.0.  No embeddings or
      HDBSCAN are used.

    * **Semantic branch** (``partition_spec`` is ``None``): runs HDBSCAN soft
      clustering on the movie embeddings, optionally guided by a concept string.

    In both cases, if ``target_cluster_id`` resolves to a concrete cluster,
    sibling clusters from the parent snapshot are carried forward unchanged
    alongside the new sub-clusters (no FOCUS-like narrowing).

    Attributes:
        target_cluster_id: Cluster to split; ``None`` = full set or unclustered state.
        concept:           Semantic concept to guide clustering (semantic branch only).
        partition_spec:    Attribute and optional bins (deterministic branch only).
        embedding_spaces:  Modalities to fuse for embedding loading (semantic branch).
        confidence:        LLM confidence [0, 1].
        target_n_clusters: Exact cluster count requested by the oracle (semantic branch).
                           ``None`` preserves the emergent HDBSCAN count.
        reuse_concept_id:  UUID of a persisted concept whose normalized scores should be
                           reused for clustering.  Set by the coordinator when the user is
                           confirming a concept-axis beeswarm proposal; never extracted from
                           LLM output.  When non-None the concept agent call is skipped.
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = False
    CREATES_SNAPSHOT: ClassVar[bool] = True
    READS_CLUSTERS: ClassVar[bool] = True

    target_cluster_id: uuid.UUID | None
    concept: str | None
    partition_spec: PartitionSpec | None
    embedding_spaces: list[Modality]
    confidence: float
    target_n_clusters: int | None
    reuse_concept_id: uuid.UUID | None = None

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Split the target cluster (or full catalogue) into sub-groups.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reply, new snapshot id, and cost.
        """
        if self.partition_spec is not None:
            return await self._execute_deterministic(ctx)
        return await self._execute_semantic(ctx)

    async def _execute_deterministic(self, ctx: ExecutionContext) -> ActionResult:
        """Deterministic branch: group movies by exact metadata attribute.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reply, new snapshot id, and cost.
        """
        from backend.coordinator.commands._clustering import propose_bins
        from backend.coordinator.commands.impl.partition_by import partition_by

        spec = self.partition_spec  # type: ignore[assignment]

        if self.target_cluster_id is None and ctx.clusters:
            mark_awaiting(
                ctx.conversation_id,
                pending_spec=PartitionSpec(attribute=spec.attribute, bins=None),
            )
            return ActionResult(
                reply_fragment=replies.format_partition_clarification(
                    spec.attribute.value, [c.label for c in ctx.clusters]
                ),
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        if spec.attribute in _NUMERIC_ATTRIBUTES and not spec.bins:
            return self._propose_numeric_bins(ctx, spec, propose_bins)

        target_id = resolve_target_or_clarify(ctx, self.target_cluster_id)

        ctx.reporter.step("clustering")
        draft = await partition_by(
            spec=spec,
            parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            source_cluster_id=target_id,
        )

        if target_id is not None and ctx.current_cluster_snapshot_id is not None:
            draft = ClusterSnapshotDraft(
                operation=draft.operation,
                params=draft.params,
                clusters=merge_in_siblings(ctx.current_cluster_snapshot_id, target_id, draft.clusters),
                warning=draft.warning,
            )

        new_snapshot_id, step_cost, n_movies, _ = await _persist_draft(ctx, draft)
        n_new = len(draft.clusters)
        reply = replies.format_partition_reply(spec.attribute.value, n_new, n_movies)
        if draft.warning:
            reply = f"{reply}\n\n⚠ {draft.warning}"
        return ActionResult(
            reply_fragment=reply,
            cluster_snapshot_id=new_snapshot_id,
            step_cost=step_cost,
        )

    def _propose_numeric_bins(self, ctx: ExecutionContext, spec: PartitionSpec, propose_bins_fn) -> ActionResult:
        """Propose default bins to the user when a numeric split has no bins specified.

        Args:
            ctx:              Execution context.
            spec:             Partition spec with numeric attribute and no bins.
            propose_bins_fn:  The propose_bins function (injected to avoid circular import).

        Returns:
            ActionResult with proposal text and unchanged snapshot id.
        """
        from backend.coordinator.commands._clustering import resolve_movie_ids

        ctx.reporter.step("clustering")

        resolved_ids = resolve_movie_ids(
            source_cluster_id=self.target_cluster_id,
            movie_ids=None,
            parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        )
        if not resolved_ids:
            return ActionResult(
                reply_fragment=replies.UNSUPPORTED_OPERATION,
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        stats = fetch_numeric_stats(resolved_ids, spec.attribute.value)
        bins = propose_bins_fn(attribute=spec.attribute.value, stats=stats)

        raw_values = fetch_partition_values(resolved_ids, spec.attribute.value)
        bin_counts: dict[str, int] = {b.label: 0 for b in bins}
        unspecified = 0
        for mid in resolved_ids:
            value = raw_values.get(mid)
            if value is None:
                unspecified += 1
                continue
            matched = False
            for b in bins:
                lo_ok = b.min is None or float(value) >= b.min  # type: ignore[arg-type]
                hi_ok = b.max is None or float(value) < b.max  # type: ignore[arg-type]
                if lo_ok and hi_ok:
                    bin_counts[b.label] += 1
                    matched = True
                    break
            if not matched:
                unspecified += 1

        proposal_text = replies.format_bin_proposal(spec.attribute.value, bins, bin_counts, unspecified)
        confirmed_spec = PartitionSpec(attribute=spec.attribute, bins=bins)
        mark_awaiting(ctx.conversation_id, pending_spec=confirmed_spec, target_cluster_id=self.target_cluster_id)
        return ActionResult(
            reply_fragment=proposal_text,
            cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            step_cost=0.0,
        )

    async def _execute_semantic(self, ctx: ExecutionContext) -> ActionResult:
        """Semantic branch: HDBSCAN clustering, optionally guided by a concept.

        Handles three sub-paths:

        1. **Reuse**: ``reuse_concept_id`` is set — the user is confirming a previously
           proposed concept-axis beeswarm.  Scores are loaded from the DB; the concept
           agent is not invoked.

        2. **Proposal**: ``concept`` is set and ``target_n_clusters`` is None — score and
           persist the concept axis, then return a proposal message with ``axis_concept_id``
           instead of clustering.  The next turn will enter path 1.

        3. **Direct**: ``concept`` is set with a specified count, or no concept — cluster
           immediately as before.

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

        if self.reuse_concept_id is not None:
            return await self._execute_reuse_concept(ctx, target_id)

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

        if concept_rep is not None and self.target_n_clusters is None:
            return await self._propose_concept_axis(ctx, concept_rep, target_id, step_cost)

        ctx.reporter.step("clustering")
        if concept_rep is not None:
            draft = await _concept_cluster(
                source_cluster_id=target_id,
                concept=concept_rep,
                parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                embedding_spaces=self.embedding_spaces,
                target_n_clusters=self.target_n_clusters,
            )
        else:
            draft = await _free_cluster(
                source_cluster_id=target_id,
                parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                embedding_spaces=self.embedding_spaces,
                target_n_clusters=self.target_n_clusters,
            )

        if target_id is not None and ctx.current_cluster_snapshot_id is not None:
            draft = ClusterSnapshotDraft(
                operation=draft.operation,
                params=draft.params,
                clusters=merge_in_siblings(ctx.current_cluster_snapshot_id, target_id, draft.clusters),
            )

        new_snapshot_id, persist_cost, n_movies, new_clusters = await _persist_draft(ctx, draft, step_cost)
        labels = [c.label for c in new_clusters]
        return ActionResult(
            reply_fragment=replies.format_drill_down_reply(labels, len(new_clusters), n_movies),
            cluster_snapshot_id=new_snapshot_id,
            step_cost=persist_cost,
        )

    async def _propose_concept_axis(
        self,
        ctx: ExecutionContext,
        concept_rep: "LinearAxisRep",
        target_id: uuid.UUID | None,
        step_cost: float,
    ) -> ActionResult:
        """Score, normalize, and persist a concept axis; return a proposal without clustering.

        Computes per-movie axis projections, normalizes them to [-1, 1] via min-max,
        persists them to the concept_scores table, then sets the awaiting flag and
        returns a reply that invites the user to inspect the beeswarm distribution.

        Args:
            ctx:         Execution context.
            concept_rep: Concept representation produced by the concept agent.
            target_id:   Resolved source cluster UUID, or None for the full catalogue.
            step_cost:   Concept-agent cost already incurred this step.

        Returns:
            ActionResult with the proposal text, unchanged snapshot id, and
            the persisted concept's UUID in ``axis_concept_id``.

        Raises:
            ValueError: If no movies or embeddings are found for scoring.
        """
        import numpy as np

        from backend.agents.concept.scoring import normalize_axis_scores, score_movies
        from backend.coordinator.commands._clustering import resolve_movie_ids
        from backend.data_access.concepts.queries import create_concept, upsert_concept_scores

        ctx.reporter.step("clustering")

        resolved_ids = resolve_movie_ids(
            source_cluster_id=target_id,
            movie_ids=None,
            parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        )
        if not resolved_ids:
            raise ValueError("No movies found for concept axis scoring")

        src = str(target_id) if target_id else "full catalogue"
        if concept_rep.space == "visual":
            modal_data = fetch_modality_embeddings(resolved_ids, ["trailer"])
            emb_map: dict = {mid: v.tolist() for mid, v in modal_data["trailer"].items()}
        else:
            emb_map = fetch_text_embeddings(resolved_ids)
        available_ids = [mid for mid in resolved_ids if mid in emb_map]
        if not available_ids:
            raise ValueError(f"No embeddings found for {src}")

        raw_scores = score_movies(concept_rep, available_ids, emb_map)
        if not raw_scores:
            raise ValueError(f"No embeddings found for {src}")

        normalized = normalize_axis_scores(raw_scores)
        if not normalized:
            raise ValueError(f"No embeddings found for {src}")

        concept_id = create_concept(
            name=concept_rep.concept_name,
            concept_type="linear_axis",
            definition={
                "concept_name": concept_rep.concept_name,
                "positive_label": getattr(concept_rep, "positive_label", ""),
                "negative_label": getattr(concept_rep, "negative_label", ""),
            },
        )
        upsert_concept_scores(concept_id, normalized)

        mark_awaiting(
            ctx.conversation_id,
            pending_concept=PendingConcept(
                concept_id=concept_id,
                concept_name=concept_rep.concept_name,
                target_cluster_id=target_id,
                embedding_spaces=self.embedding_spaces,
            ),
        )

        log.info(
            "concept_axis_proposed",
            extra={
                "concept_id": str(concept_id),
                "concept": concept_rep.concept_name,
                "n_movies": len(normalized),
                "conversation_id": str(ctx.conversation_id),
            },
        )
        return ActionResult(
            reply_fragment=replies.format_axis_proposal(concept_rep.concept_name, len(normalized)),
            cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            step_cost=step_cost,
            axis_concept_id=concept_id,
        )

    async def _execute_reuse_concept(
        self,
        ctx: ExecutionContext,
        target_id: uuid.UUID | None,
    ) -> ActionResult:
        """Cluster using previously persisted concept scores, skipping the concept agent.

        Called when ``reuse_concept_id`` is set (user is confirming a concept-axis
        beeswarm proposal). Loads the normalized scores from ``concept_scores``,
        runs ``_build_concept_clusters``, merges siblings, persists, and replies.

        Args:
            ctx:       Execution context.
            target_id: Resolved source cluster UUID (from the pending concept context).

        Returns:
            ActionResult with the drill-down reply and the new snapshot id.

        Raises:
            ValueError: If no concept scores are found for the given concept id.
        """
        from backend.data_access.concepts.queries import get_concept, get_concept_scores

        assert self.reuse_concept_id is not None

        ctx.reporter.step("clustering")

        concept_row = get_concept(self.reuse_concept_id)
        if concept_row is None:
            raise ValueError(f"Concept {self.reuse_concept_id} not found for reuse clustering")

        score_rows = get_concept_scores(self.reuse_concept_id)
        if not score_rows:
            raise ValueError(f"No concept scores found for concept {self.reuse_concept_id}")

        scores = {r.movie_id: r.score for r in score_rows}
        available_ids = list(scores)

        draft = _build_concept_clusters(
            concept_name=concept_row.name,
            concept_space=None,
            scores=scores,
            available_ids=available_ids,
            parent_cluster_ref=target_id,
            source_cluster_id=target_id,
            parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            embedding_spaces=self.embedding_spaces,
            target_n_clusters=self.target_n_clusters,
        )

        if target_id is not None and ctx.current_cluster_snapshot_id is not None:
            draft = ClusterSnapshotDraft(
                operation=draft.operation,
                params=draft.params,
                clusters=merge_in_siblings(ctx.current_cluster_snapshot_id, target_id, draft.clusters),
            )

        new_snapshot_id, persist_cost, n_movies, new_clusters = await _persist_draft(ctx, draft)
        labels = [c.label for c in new_clusters]
        return ActionResult(
            reply_fragment=replies.format_drill_down_reply(labels, len(new_clusters), n_movies),
            cluster_snapshot_id=new_snapshot_id,
            step_cost=persist_cost,
        )
