from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.coordinator.commands.helpers.bins import NUMERIC_ATTRIBUTES
from backend.coordinator.commands.helpers.drafts import merge_in_siblings, persist_draft
from backend.coordinator.commands.helpers.targets import resolve_target_or_clarify
from backend.coordinator.tools.clarification_state import mark_awaiting
from backend.agents.intent.types import PartitionSpec
from backend.agents.responder import replies
from backend.coordinator.types import ClusterSnapshotDraft
from backend.data_access.movies.queries import fetch_numeric_stats, fetch_partition_values

if TYPE_CHECKING:
    from backend.coordinator.commands.impl.cluster.command import ClusterCommand

log = logging.getLogger(__name__)


async def execute_deterministic(cmd: ClusterCommand, ctx: ExecutionContext) -> ActionResult:
    """Deterministic branch: group movies by exact metadata attribute.

    Args:
        cmd: The ``ClusterCommand`` being executed.
        ctx: Execution context with session state.

    Returns:
        ActionResult with reply, new snapshot id, and cost.
    """
    from backend.coordinator.commands.helpers.bins import propose_bins
    from backend.coordinator.commands.impl.partition_by import partition_by

    spec = cmd.partition_spec  # type: ignore[assignment]

    if cmd.target_cluster_id is None and ctx.clusters:
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

    if spec.attribute in NUMERIC_ATTRIBUTES and not spec.bins:
        return propose_numeric_bins(cmd, ctx, propose_bins)

    target_id = resolve_target_or_clarify(ctx, cmd.target_cluster_id)

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

    new_snapshot_id, step_cost, n_movies, _ = await persist_draft(ctx, draft)
    n_new = len(draft.clusters)
    reply = replies.format_partition_reply(spec.attribute.value, n_new, n_movies)
    if draft.warning:
        reply = f"{reply}\n\n⚠ {draft.warning}"
    return ActionResult(
        reply_fragment=reply,
        cluster_snapshot_id=new_snapshot_id,
        step_cost=step_cost,
    )


def propose_numeric_bins(cmd: ClusterCommand, ctx: ExecutionContext, propose_bins_fn) -> ActionResult:
    """Propose default bins to the user when a numeric split has no bins specified.

    Args:
        cmd:              The ``ClusterCommand`` being executed.
        ctx:              Execution context.
        propose_bins_fn:  The propose_bins function (injected to avoid circular import).

    Returns:
        ActionResult with proposal text and unchanged snapshot id.
    """
    from backend.coordinator.commands.helpers.movies import resolve_movie_ids

    ctx.reporter.step("clustering")

    spec = cmd.partition_spec  # type: ignore[assignment]
    resolved_ids = resolve_movie_ids(
        source_cluster_id=cmd.target_cluster_id,
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
    mark_awaiting(ctx.conversation_id, pending_spec=confirmed_spec, target_cluster_id=cmd.target_cluster_id)
    return ActionResult(
        reply_fragment=proposal_text,
        cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        step_cost=0.0,
    )
