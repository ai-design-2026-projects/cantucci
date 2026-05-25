"""Per-action handlers and dispatch logic for the Coordinator.

Each handler takes an ``ActionContext`` and returns a ``(reply_fragment,
new_cluster_snapshot_id, step_cost)`` tuple.  ``execute_action`` dispatches
to the correct handler based on the action's mode (``NavigationMode`` or
``DialogueMode``), preserving the original semantics including the
RESET-on-None-snapshot fallback.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from backend.agents.clustering.agent import apply_navigation
from backend.agents.clustering.types import NavigationMode, NavigationRequest
from backend.agents.concept.agent import build_concept
from backend.agents.responder import replies
from backend.agents.coordinator.tools.progress import ProgressReporter
from backend.agents.coordinator.types import sentinel_cluster_snapshot_id
from backend.agents.explanation.agent import explain_placement
from backend.agents.intent.types import DialogueMode, IntentAction
from backend.data_access.cluster_snapshots.queries import (
    get_cluster_snapshot_with_clusters,
    get_root_cluster_snapshot,
    record_conversation_snapshot_ref,
)
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.data_access.conversations.queries import set_current_cluster_snapshot
from backend.data_access.conversations.types import ConversationRow
from backend.data_access.movies.queries import list_movie_ids


@dataclass(frozen=True, slots=True)
class ActionContext:
    """Immutable bundle of per-action inputs threaded through the handler pipeline.

    Attributes:
        action:                      The classified action to execute.
        current_cluster_snapshot_id: Active cluster snapshot before this action.
        clusters:                    Cluster list for the current snapshot.
        conversation_id:             Conversation UUID.
        conversation_row:            Current conversation state.
        message_id:                  Current message UUID for LLM logging.
        accumulated_cost:            Running LLM cost before this action.
        reporter:                    SSE progress reporter for this turn.
    """

    action: IntentAction
    current_cluster_snapshot_id: uuid.UUID | None
    clusters: list[ClusterRow]
    conversation_id: uuid.UUID
    conversation_row: ConversationRow
    message_id: uuid.UUID
    accumulated_cost: float
    reporter: ProgressReporter


_Handler = Callable[[ActionContext], Awaitable[tuple[str, uuid.UUID | None, float]]]


async def handle_small_talk(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Handle a SMALL_TALK action with a static help reply.

    Args:
        ctx: Action context.

    Returns:
        Tuple of (static reply, unchanged snapshot id, 0.0 cost).
    """
    return replies.SMALL_TALK, ctx.current_cluster_snapshot_id, 0.0


async def handle_reset(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Return to the root (base) cluster snapshot for this conversation.

    Args:
        ctx: Action context.

    Returns:
        Tuple of (reply text, root snapshot id, 0.0 cost).
    """
    root = get_root_cluster_snapshot()
    if root is None:
        return replies.NO_BASE_SNAPSHOT, sentinel_cluster_snapshot_id(), 0.0
    set_current_cluster_snapshot(ctx.conversation_id, root.id)
    record_conversation_snapshot_ref(ctx.conversation_id, root.id)
    cswc = get_cluster_snapshot_with_clusters(root.id)
    n = len(cswc.clusters) if cswc else 0
    return replies.format_reset_reply(n), root.id, 0.0


async def handle_explain(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Handle an EXPLAIN action by finding the target movie and calling the explanation agent.

    Args:
        ctx: Action context.  ``ctx.action.target_cluster_id`` selects the target cluster;
             falls back to the first cluster when None.

    Returns:
        Tuple of (explanation text, unchanged snapshot id, 0.0 cost).
    """
    ctx.reporter.step("explain")
    target_cluster = (
        next((c for c in ctx.clusters if c.id == ctx.action.target_cluster_id), None)
        if ctx.action.target_cluster_id else (ctx.clusters[0] if ctx.clusters else None)
    )
    if target_cluster is None or not target_cluster.exemplar_movie_ids:
        return replies.EXPLAIN_TARGET_UNCLEAR, ctx.current_cluster_snapshot_id, 0.0

    movie_id = target_cluster.exemplar_movie_ids[0]
    result = await explain_placement(
        movie_id=movie_id,
        cluster_id=target_cluster.id,
        cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        conversation_id=ctx.conversation_id,
        message_id=ctx.message_id,
        accumulated_cost=ctx.accumulated_cost,
    )
    return result.text, ctx.current_cluster_snapshot_id, 0.0


async def handle_drill_down(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Handle a DRILL_DOWN action by splitting the target cluster into sub-clusters.

    Args:
        ctx: Action context.  ``ctx.action.target_cluster_id`` selects the cluster to split;
             falls back to the first cluster when None.  ``ctx.action.concept`` optionally
             guides the split with a semantic concept.

    Returns:
        Tuple of (reply text, new snapshot id, cumulative step cost).
    """
    target_id = ctx.action.target_cluster_id or (ctx.clusters[0].id if ctx.clusters else None)
    if target_id is None:
        return replies.NO_CLUSTER_TO_SPLIT, ctx.current_cluster_snapshot_id, 0.0

    step_cost = 0.0
    concept = None
    if ctx.action.concept:
        ctx.reporter.step("concept")
        concept = await build_concept(
            ctx.action.concept, ctx.conversation_id, ctx.message_id, ctx.accumulated_cost + step_cost
        )
        step_cost += concept.cost

    ctx.reporter.step("clustering")
    new_cluster_snapshot_id = await apply_navigation(NavigationRequest(
        mode=NavigationMode.DRILL_DOWN,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        conversation_id=ctx.conversation_id,
        accumulated_cost=ctx.accumulated_cost + step_cost,
        concept=concept,
        source_cluster_id=target_id,
        embedding_spaces=ctx.action.embedding_spaces,
    ))
    new_cswc = get_cluster_snapshot_with_clusters(new_cluster_snapshot_id)
    n_new = len(new_cswc.clusters) if new_cswc else 0
    labels = [c.label for c in (new_cswc.clusters if new_cswc else [])]
    return replies.format_drill_down_reply(labels, n_new), new_cluster_snapshot_id, step_cost


async def handle_merge(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Handle a MERGE action by combining the first two clusters in the current snapshot.

    Args:
        ctx: Action context.

    Returns:
        Tuple of (reply text, new snapshot id, 0.0 cost).
    """
    if len(ctx.clusters) < 2:
        return replies.FEWER_THAN_TWO_TO_MERGE, ctx.current_cluster_snapshot_id, 0.0

    ids_to_merge = [c.id for c in ctx.clusters[:2]]
    ctx.reporter.step("clustering")
    new_cluster_snapshot_id = await apply_navigation(NavigationRequest(
        mode=NavigationMode.MERGE,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        conversation_id=ctx.conversation_id,
        accumulated_cost=ctx.accumulated_cost,
        cluster_ids=ids_to_merge,
        merged_label=ctx.action.merged_label or "Merged",
    ))
    return replies.MERGE_REPLY, new_cluster_snapshot_id, 0.0


async def handle_recut(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Handle a RECUT action by re-clustering the full movie catalogue.

    Args:
        ctx: Action context.  ``ctx.action.concept`` optionally guides the re-clustering.

    Returns:
        Tuple of (reply text, new snapshot id, cumulative step cost).
    """
    all_movie_ids = list_movie_ids()
    step_cost = 0.0
    concept = None
    if ctx.action.concept:
        ctx.reporter.step("concept")
        concept = await build_concept(
            ctx.action.concept, ctx.conversation_id, ctx.message_id, ctx.accumulated_cost + step_cost
        )
        step_cost += concept.cost

    ctx.reporter.step("clustering")
    new_cluster_snapshot_id = await apply_navigation(NavigationRequest(
        mode=NavigationMode.RECUT,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        conversation_id=ctx.conversation_id,
        accumulated_cost=ctx.accumulated_cost + step_cost,
        concept=concept,
        movie_ids=all_movie_ids,
        embedding_spaces=ctx.action.embedding_spaces,
    ))
    new_cswc = get_cluster_snapshot_with_clusters(new_cluster_snapshot_id)
    n_new = len(new_cswc.clusters) if new_cswc else 0
    return replies.format_recut_reply(n_new), new_cluster_snapshot_id, step_cost


async def handle_focus(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Handle a FOCUS action by narrowing the snapshot to a single cluster's members.

    Args:
        ctx: Action context.  ``ctx.action.target_cluster_id`` selects the cluster to focus on;
             falls back to the first cluster when None.

    Returns:
        Tuple of (reply text, new snapshot id, 0.0 cost).
    """
    target_id = ctx.action.target_cluster_id or (ctx.clusters[0].id if ctx.clusters else None)
    if target_id is None:
        return replies.NO_CLUSTER_TO_SPLIT, ctx.current_cluster_snapshot_id, 0.0

    target_cluster = next((c for c in ctx.clusters if c.id == target_id), None)

    ctx.reporter.step("clustering")
    new_cluster_snapshot_id = await apply_navigation(NavigationRequest(
        mode=NavigationMode.FOCUS,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        conversation_id=ctx.conversation_id,
        accumulated_cost=ctx.accumulated_cost,
        source_cluster_id=target_id,
    ))
    new_cswc = get_cluster_snapshot_with_clusters(new_cluster_snapshot_id)
    n_members = sum(len(c.exemplar_movie_ids) for c in (new_cswc.clusters if new_cswc else []))
    label = target_cluster.label if target_cluster else None
    return replies.format_focus_reply(label, n_members), new_cluster_snapshot_id, 0.0


async def handle_cross_filter(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Handle a CROSS_FILTER action by filtering by metadata then re-clustering survivors.

    Args:
        ctx: Action context.  ``ctx.action.metadata_filter`` carries the predicate.
             ``ctx.action.concept`` optionally guides clustering of the filtered set.

    Returns:
        Tuple of (reply text, new snapshot id, cumulative step cost).
    """
    if ctx.action.metadata_filter is None:
        return replies.UNSUPPORTED_OPERATION, ctx.current_cluster_snapshot_id, 0.0

    step_cost = 0.0
    concept = None
    if ctx.action.concept:
        ctx.reporter.step("concept")
        concept = await build_concept(
            ctx.action.concept, ctx.conversation_id, ctx.message_id, ctx.accumulated_cost + step_cost
        )
        step_cost += concept.cost

    ctx.reporter.step("clustering")
    new_cluster_snapshot_id = await apply_navigation(NavigationRequest(
        mode=NavigationMode.CROSS_FILTER,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        conversation_id=ctx.conversation_id,
        accumulated_cost=ctx.accumulated_cost + step_cost,
        concept=concept,
        metadata_filter=ctx.action.metadata_filter,
        embedding_spaces=ctx.action.embedding_spaces,
    ))
    new_cswc = get_cluster_snapshot_with_clusters(new_cluster_snapshot_id)
    n_new = len(new_cswc.clusters) if new_cswc else 0
    return replies.format_cross_filter_reply(n_new), new_cluster_snapshot_id, step_cost


_DISPATCH: dict[NavigationMode | DialogueMode, _Handler] = {
    DialogueMode.SMALL_TALK: handle_small_talk,
    DialogueMode.EXPLAIN: handle_explain,
    NavigationMode.DRILL_DOWN: handle_drill_down,
    NavigationMode.MERGE: handle_merge,
    NavigationMode.RECUT: handle_recut,
    NavigationMode.FOCUS: handle_focus,
    NavigationMode.CROSS_FILTER: handle_cross_filter,
}


async def execute_action(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Dispatch a single classified action to its handler and return the result.

    RESET (and any action when no snapshot exists) is handled before the dispatch
    table to preserve the original fallback semantics: if the conversation has no
    active snapshot, state-changing operations implicitly reset to root.

    Args:
        ctx: Immutable bundle of action inputs.

    Returns:
        Tuple of (reply_fragment, new_cluster_snapshot_id, step_cost).
    """
    if ctx.action.mode == DialogueMode.RESET or ctx.current_cluster_snapshot_id is None:
        return await handle_reset(ctx)

    handler = _DISPATCH.get(ctx.action.mode)
    if handler is None:
        return replies.UNSUPPORTED_OPERATION, ctx.current_cluster_snapshot_id, 0.0
    return await handler(ctx)
