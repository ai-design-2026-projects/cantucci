import uuid

from backend.coordinator.commands.base import ActionResult, ExecutionContext


def resolve_target_or_clarify(
    ctx: ExecutionContext, target_cluster_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Resolve a target cluster ID, auto-selecting when exactly one cluster is active.

    Returns a concrete cluster UUID when the target can be determined without user
    input:
      - If ``target_cluster_id`` is already set, return it directly.
      - If exactly one cluster is active, return that cluster's ID (deterministic
        shortcut — no clarification needed when there is no ambiguity).
      - Otherwise return ``None``: the caller should request clarification (2+ clusters)
        or fall back to the whole-catalogue path (0 clusters).

    Args:
        ctx:               Execution context carrying the current cluster list.
        target_cluster_id: Cluster UUID from the intent agent, or ``None`` if not named.

    Returns:
        Resolved cluster UUID, or ``None`` when ambiguous or no clusters exist.
    """
    if target_cluster_id is not None:
        return target_cluster_id
    if len(ctx.clusters) == 1:
        return ctx.clusters[0].id
    return None


def clarify_ambiguous_target(ctx: ExecutionContext) -> ActionResult | None:
    """Return a clarification ActionResult when the target cluster is ambiguous, else None.

    Should be called after ``resolve_target_or_clarify`` returns ``None`` and
    ``ctx.clusters`` is non-empty (2+ clusters exist but none was specified).
    Marks the conversation as awaiting a clarification reply and returns the
    clarification message.  When there are no clusters at all, returns ``None``
    so the caller can fall through to the whole-catalogue path.

    Args:
        ctx: Execution context carrying the current cluster list.

    Returns:
        ``ActionResult`` with the clarification message, or ``None`` when
        ``ctx.clusters`` is empty.
    """
    from backend.agents.responder import replies
    from backend.coordinator.tools.clarification_state import mark_awaiting

    if not ctx.clusters:
        return None
    mark_awaiting(ctx.conversation_id)
    return ActionResult(
        reply_fragment=replies.format_cluster_clarification([c.label for c in ctx.clusters]),
        cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        step_cost=0.0,
    )
