import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from backend.agents.clustering.agent import cross_filter, drill_down, focus, merge_clusters, partition_by
from backend.agents.clustering.types import NavigationMode, PartitionAttribute, PartitionSpec
from backend.agents.coordinator.tools.clarification_state import mark_awaiting
from backend.agents.coordinator.tools.labeling import label_unlabeled_clusters
from backend.agents.coordinator.tools.persist import persist_and_label
from backend.agents.concept.agent import build_concept
from backend.agents.clustering.partition_bins import propose_bins
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
from backend.data_access.movies.queries import fetch_numeric_stats, fetch_partition_values

_NUMERIC_ATTRIBUTES = {
    PartitionAttribute.RUNTIME,
    PartitionAttribute.RELEASE_YEAR,
    PartitionAttribute.VOTE_AVERAGE,
}


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
    """Move the conversation to the unclustered state (no active snapshot).

    Args:
        ctx: Action context.

    Returns:
        Tuple of (reply text, None, 0.0 cost).
    """
    set_current_cluster_snapshot(ctx.conversation_id, None)
    return replies.RESET_REPLY, None, 0.0


async def handle_go_to_base(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Navigate to the pre-computed ingest-time base cluster snapshot.

    Labels any unlabeled base clusters so they are immediately visible to the user.

    Args:
        ctx: Action context.

    Returns:
        Tuple of (reply text, root snapshot id, labeling cost).
    """
    root = get_root_cluster_snapshot()
    if root is None:
        return replies.NO_BASE_SNAPSHOT, sentinel_cluster_snapshot_id(), 0.0
    set_current_cluster_snapshot(ctx.conversation_id, root.id)
    record_conversation_snapshot_ref(ctx.conversation_id, root.id)
    cswc = get_cluster_snapshot_with_clusters(root.id)
    clusters = cswc.clusters if cswc else []
    label_cost = 0.0
    if any(c.label is None for c in clusters):
        ctx.reporter.step("labeling")
        clusters, label_cost = await label_unlabeled_clusters(
            clusters, ctx.conversation_id, ctx.message_id, ctx.accumulated_cost
        )
    return replies.format_reset_reply(len(clusters)), root.id, label_cost


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

    When no target cluster is specified and clusters already exist, returns a clarification
    question listing the current clusters.  When no clusters exist (unclustered state),
    proceeds with full-catalogue clustering as the initial clustering path.

    Args:
        ctx: Action context.  ``ctx.action.target_cluster_id`` selects the cluster to split;
             ``None`` triggers a clarification when clusters exist, or full-catalogue
             clustering from the unclustered state.  ``ctx.action.concept`` optionally
             guides the split with a semantic concept.

    Returns:
        Tuple of (reply text, new snapshot id, cumulative step cost).
    """
    target_id = ctx.action.target_cluster_id
    if target_id is None and ctx.clusters:
        mark_awaiting(ctx.conversation_id)
        return (
            replies.format_drill_down_clarification([c.label for c in ctx.clusters]),
            ctx.current_cluster_snapshot_id,
            0.0,
        )

    step_cost = 0.0
    concept = None
    if ctx.action.concept:
        ctx.reporter.step("concept")
        concept = await build_concept(
            ctx.action.concept, ctx.conversation_id, ctx.message_id, ctx.accumulated_cost + step_cost
        )
        step_cost += concept.cost

    ctx.reporter.step("clustering")
    draft = await drill_down(
        source_cluster_id=target_id,
        concept=concept,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        embedding_spaces=ctx.action.embedding_spaces,
    )
    n_movies = len({mid for c in draft.clusters for mid, _ in c.memberships})
    new_cluster_snapshot_id, label_cost = await persist_and_label(
        draft, ctx.conversation_id, ctx.current_cluster_snapshot_id, ctx.accumulated_cost + step_cost
    )
    step_cost += label_cost
    new_cswc = get_cluster_snapshot_with_clusters(new_cluster_snapshot_id)
    n_new = len(new_cswc.clusters) if new_cswc else 0
    labels = [c.label for c in (new_cswc.clusters if new_cswc else [])]
    return replies.format_drill_down_reply(labels, n_new, n_movies), new_cluster_snapshot_id, step_cost


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
    draft = await merge_clusters(
        cluster_ids=ids_to_merge,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        merged_label=ctx.action.merged_label or "Merged",
    )
    new_cluster_snapshot_id, label_cost = await persist_and_label(
        draft, ctx.conversation_id, ctx.current_cluster_snapshot_id, ctx.accumulated_cost
    )
    return replies.MERGE_REPLY, new_cluster_snapshot_id, label_cost


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
    draft = await focus(
        source_cluster_id=target_id,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
    )
    new_cluster_snapshot_id, label_cost = await persist_and_label(
        draft, ctx.conversation_id, ctx.current_cluster_snapshot_id, ctx.accumulated_cost
    )
    n_members = len({mid for mid, _ in draft.clusters[0].memberships}) if draft.clusters else 0
    label = target_cluster.label if target_cluster else None
    return replies.format_focus_reply(label, n_members), new_cluster_snapshot_id, label_cost


async def handle_partition_by(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Handle a PARTITION_BY action by grouping movies into deterministic attribute buckets.

    When no target cluster is specified and clusters already exist, returns a clarification
    question listing the current clusters.  When no clusters exist (unclustered state),
    proceeds with full-catalogue partitioning as the initial partition path.

    When the intent specifies a numeric attribute without bins, intercepts before
    execution and instead calls the partition advisor to propose bins to the user.
    The conversation is marked as awaiting confirmation; on the next turn the intent
    agent re-classifies with the proposed bins as context and executes normally.

    Args:
        ctx: Action context.  ``ctx.action.partition_spec`` carries the attribute and bins.
             ``ctx.action.target_cluster_id`` scopes the partition; ``None`` triggers a
             clarification when clusters exist, or full-catalogue partitioning from the
             unclustered state.

    Returns:
        Tuple of (reply text, new snapshot id, step cost).
    """
    if ctx.action.partition_spec is None:
        return replies.UNSUPPORTED_OPERATION, ctx.current_cluster_snapshot_id, 0.0

    if ctx.action.target_cluster_id is None and ctx.clusters:
        mark_awaiting(ctx.conversation_id)
        return (
            replies.format_partition_clarification([c.label for c in ctx.clusters]),
            ctx.current_cluster_snapshot_id,
            0.0,
        )

    spec = ctx.action.partition_spec

    if spec.attribute in _NUMERIC_ATTRIBUTES and not spec.bins:
        return _propose_numeric_bins(ctx, spec)

    ctx.reporter.step("clustering")
    draft = await partition_by(
        spec=spec,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        source_cluster_id=ctx.action.target_cluster_id,
    )
    n_movies = len({mid for c in draft.clusters for mid, _ in c.memberships})
    new_cluster_snapshot_id, label_cost = await persist_and_label(
        draft, ctx.conversation_id, ctx.current_cluster_snapshot_id, ctx.accumulated_cost
    )
    n_new = len(draft.clusters)
    return (
        replies.format_partition_reply(spec.attribute.value, n_new, n_movies),
        new_cluster_snapshot_id,
        label_cost,
    )


def _propose_numeric_bins(
    ctx: ActionContext, spec: PartitionSpec
) -> tuple[str, uuid.UUID | None, float]:
    """Propose default bins to the user when a numeric partition_by has no bins specified.

    Resolves the in-scope movie set, fetches distribution stats, computes labelled bins
    deterministically, counts movies per bin, and returns a proposal message. Marks the
    conversation as awaiting so the next turn passes the proposal as clarification context
    to the intent agent.

    Args:
        ctx:  Action context.
        spec: The partition spec with a numeric attribute and no bins.

    Returns:
        Tuple of (proposal text, unchanged snapshot id, 0.0 cost).
    """
    from backend.agents.clustering.operations._helpers import resolve_movie_ids

    ctx.reporter.step("clustering")

    resolved_ids = resolve_movie_ids(
        source_cluster_id=ctx.action.target_cluster_id,
        movie_ids=None,
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
    )
    if not resolved_ids:
        return replies.UNSUPPORTED_OPERATION, ctx.current_cluster_snapshot_id, 0.0

    stats = fetch_numeric_stats(resolved_ids, spec.attribute.value)
    bins = propose_bins(attribute=spec.attribute.value, stats=stats)

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
    mark_awaiting(ctx.conversation_id)
    return proposal_text, ctx.current_cluster_snapshot_id, 0.0


async def handle_cross_filter(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """Handle a CROSS_FILTER action by filtering movies by metadata.

    Produces a snapshot with a single cluster containing the surviving movies.
    No clustering is performed; the user can follow up with a drill_down to cluster them.

    Args:
        ctx: Action context.  ``ctx.action.metadata_filter`` carries the predicate.

    Returns:
        Tuple of (reply text, new snapshot id, label cost).
    """
    if ctx.action.metadata_filter is None:
        return replies.UNSUPPORTED_OPERATION, ctx.current_cluster_snapshot_id, 0.0

    ctx.reporter.step("clustering")
    draft = await cross_filter(
        parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        metadata_filter=ctx.action.metadata_filter,
    )
    n_movies = len({mid for c in draft.clusters for mid, _ in c.memberships})
    new_cluster_snapshot_id, label_cost = await persist_and_label(
        draft, ctx.conversation_id, ctx.current_cluster_snapshot_id, ctx.accumulated_cost
    )
    return replies.format_cross_filter_reply(n_movies), new_cluster_snapshot_id, label_cost


_DISPATCH: dict[NavigationMode | DialogueMode, _Handler] = {
    DialogueMode.SMALL_TALK: handle_small_talk,
    DialogueMode.GO_TO_BASE: handle_go_to_base,
    DialogueMode.EXPLAIN: handle_explain,
    NavigationMode.DRILL_DOWN: handle_drill_down,
    NavigationMode.MERGE: handle_merge,
    NavigationMode.FOCUS: handle_focus,
    NavigationMode.CROSS_FILTER: handle_cross_filter,
    NavigationMode.PARTITION_BY: handle_partition_by,
}


async def execute_action(ctx: ActionContext) -> tuple[str, uuid.UUID | None, float]:
    """
    Dispatch a single classified action to its handler and return the result.
    Args:
        ctx: Immutable bundle of action inputs.
    Returns:
        Tuple of (reply_fragment, new_cluster_snapshot_id, step_cost).
    """
    if ctx.action.mode == DialogueMode.RESET:
        return await handle_reset(ctx)

    handler = _DISPATCH.get(ctx.action.mode)
    if handler is None:
        return replies.UNSUPPORTED_OPERATION, ctx.current_cluster_snapshot_id, 0.0
    return await handler(ctx)
