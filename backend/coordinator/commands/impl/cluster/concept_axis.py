from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from backend.agents.concept.types import PendingConcept
from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.coordinator.commands.helpers.drafts import persist_draft
from backend.coordinator.commands.helpers.drafts import merge_in_siblings
from backend.coordinator.commands.impl.cluster.building import build_concept_clusters
from backend.coordinator.tools.clarification_state import mark_awaiting
from backend.agents.responder import replies
from backend.data_access.movies.queries import fetch_modality_embeddings, fetch_text_embeddings

if TYPE_CHECKING:
    from backend.agents.concept.types import LinearAxisRep
    from backend.coordinator.commands.impl.cluster.command import ClusterCommand

log = logging.getLogger(__name__)


async def propose_concept_axis(
    cmd: ClusterCommand,
    ctx: ExecutionContext,
    concept_rep: LinearAxisRep,
    target_id: uuid.UUID | None,
    step_cost: float,
) -> ActionResult:
    """Score, normalize, and persist a concept axis; return a proposal without clustering.

    Computes per-movie axis projections, normalizes them to [-1, 1] via min-max,
    persists them to the concept_scores table, then sets the awaiting flag and
    returns a reply that invites the user to inspect the beeswarm distribution.

    Args:
        cmd:         The ``ClusterCommand`` being executed.
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
    from backend.agents.concept.scoring import normalize_axis_scores, score_movies
    from backend.coordinator.commands.helpers.movies import resolve_movie_ids
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
            "space": getattr(concept_rep, "space", "semantic"),
        },
    )
    upsert_concept_scores(concept_id, normalized)

    mark_awaiting(
        ctx.conversation_id,
        pending_concept=PendingConcept(
            concept_id=concept_id,
            concept_name=concept_rep.concept_name,
            target_cluster_id=target_id,
            embedding_spaces=cmd.embedding_spaces,
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


async def execute_reuse_concept(
    cmd: ClusterCommand,
    ctx: ExecutionContext,
    target_id: uuid.UUID | None,
) -> ActionResult:
    """Cluster using previously persisted concept scores, skipping the concept agent.

    Called when ``reuse_concept_id`` is set (user is confirming a concept-axis
    beeswarm proposal). Loads the normalized scores from ``concept_scores``,
    runs ``build_concept_clusters``, merges siblings, persists, and replies.

    Args:
        cmd:       The ``ClusterCommand`` being executed.
        ctx:       Execution context.
        target_id: Resolved source cluster UUID (from the pending concept context).

    Returns:
        ActionResult with the drill-down reply and the new snapshot id.

    Raises:
        ValueError: If no concept scores are found for the given concept id.
    """
    from backend.coordinator.types import ClusterSnapshotDraft
    from backend.data_access.concepts.queries import get_concept, get_concept_scores

    assert cmd.reuse_concept_id is not None

    ctx.reporter.step("clustering")

    concept_row = get_concept(cmd.reuse_concept_id)
    if concept_row is None:
        raise ValueError(f"Concept {cmd.reuse_concept_id} not found for reuse clustering")

    score_rows = get_concept_scores(cmd.reuse_concept_id)
    if not score_rows:
        raise ValueError(f"No concept scores found for concept {cmd.reuse_concept_id}")

    scores = {r.movie_id: r.score for r in score_rows}
    available_ids = list(scores)

    draft = build_concept_clusters(
        concept_name=concept_row.name,
        concept_space=None,
        scores=scores,
        available_ids=available_ids,
        parent_cluster_ref=target_id,
        source_cluster_id=target_id,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        embedding_spaces=cmd.embedding_spaces,
        target_n_clusters=cmd.target_n_clusters,
    )

    if target_id is not None and ctx.current_cluster_snapshot_id is not None:
        draft = ClusterSnapshotDraft(
            operation=draft.operation,
            params=draft.params,
            clusters=merge_in_siblings(ctx.current_cluster_snapshot_id, target_id, draft.clusters),
        )

    new_snapshot_id, persist_cost, n_movies, new_clusters = await persist_draft(ctx, draft)
    labels = [c.label for c in new_clusters]
    return ActionResult(
        reply_fragment=replies.format_cluster_reply(labels, len(new_clusters), n_movies),
        cluster_snapshot_id=new_snapshot_id,
        step_cost=persist_cost,
    )
