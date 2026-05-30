from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.coordinator.commands.helpers.drafts import merge_in_siblings, persist_draft
from backend.coordinator.commands.helpers.targets import resolve_target_or_clarify
from backend.coordinator.tools.clarification_state import mark_awaiting
from backend.agents.responder import replies
from backend.coordinator.types import ClusterSnapshotDraft

if TYPE_CHECKING:
    from backend.coordinator.commands.impl.cluster.command import ClusterCommand

log = logging.getLogger(__name__)


async def execute_semantic(cmd: ClusterCommand, ctx: ExecutionContext) -> ActionResult:
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
        cmd: The ``ClusterCommand`` being executed.
        ctx: Execution context with session state.

    Returns:
        ActionResult with reply, new snapshot id, and cost.
    """
    from backend.agents.concept.agent import agent as concept_agent
    from backend.coordinator.commands.impl.cluster.building import concept_cluster, free_cluster
    from backend.coordinator.commands.impl.cluster.concept_axis import (
        execute_reuse_concept,
        propose_concept_axis,
    )

    target_id = resolve_target_or_clarify(ctx, cmd.target_cluster_id)
    if target_id is None and ctx.clusters:
        mark_awaiting(ctx.conversation_id)
        return ActionResult(
            reply_fragment=replies.format_drill_down_clarification([c.label for c in ctx.clusters]),
            cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            step_cost=0.0,
        )

    if cmd.reuse_concept_id is not None:
        return await execute_reuse_concept(cmd, ctx, target_id)

    step_cost = 0.0
    concept_rep = None
    if cmd.concept:
        ctx.reporter.step("concept")
        concept_rep = await concept_agent.run(
            concept_name=cmd.concept,
            conversation_id=ctx.conversation_id,
            message_id=ctx.message_id,
            accumulated_cost=ctx.accumulated_cost + step_cost,
        )
        step_cost += concept_rep.cost

    if concept_rep is not None and cmd.target_n_clusters is None:
        return await propose_concept_axis(cmd, ctx, concept_rep, target_id, step_cost)

    ctx.reporter.step("clustering")
    if concept_rep is not None:
        draft = await concept_cluster(
            source_cluster_id=target_id,
            concept=concept_rep,
            parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            embedding_spaces=cmd.embedding_spaces,
            target_n_clusters=cmd.target_n_clusters,
        )
    else:
        draft = await free_cluster(
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

    new_snapshot_id, persist_cost, n_movies, new_clusters = await persist_draft(ctx, draft, step_cost)
    labels = [c.label for c in new_clusters]
    return ActionResult(
        reply_fragment=replies.format_drill_down_reply(labels, len(new_clusters), n_movies),
        cluster_snapshot_id=new_snapshot_id,
        step_cost=persist_cost,
    )
