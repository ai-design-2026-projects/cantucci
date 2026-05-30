import uuid

from backend.agents.intent.types import IntentAction
from backend.coordinator.commands.base import ExecutionContext
from backend.coordinator.commands.factory import build_command
from backend.coordinator.tools.progress import ProgressReporter
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.conversations.types import ConversationRow


async def dispatch_actions(
    actions: list[IntentAction],
    conversation_id: uuid.UUID,
    conversation_row: ConversationRow,
    current_cluster_snapshot_id: uuid.UUID | None,
    accumulated_cost: float,
    message_id: uuid.UUID,
    reporter: ProgressReporter,
) -> tuple[uuid.UUID | None, float, list[str], uuid.UUID | None]:
    """Execute each action in sequence, threading the cluster snapshot forward.

    Clusters are re-read from the DB at the start of each action so later
    steps see the actual post-operation state from prior steps.

    Args:
        actions:                      Classified actions to dispatch.
        conversation_id:              Conversation UUID.
        conversation_row:             Pre-loaded conversation row.
        current_cluster_snapshot_id:  Active snapshot before this batch.
        accumulated_cost:             Running LLM cost before dispatch.
        message_id:                   Current message UUID for logging.
        reporter:                     SSE progress reporter.

    Returns:
        Tuple of (final_cluster_snapshot_id, accumulated_cost, reply_fragments,
        axis_concept_id).  ``axis_concept_id`` is the last non-None value produced
        by any action in this batch; None when no action proposed a concept axis.
    """
    reply_fragments: list[str] = []
    axis_concept_id: uuid.UUID | None = None
    for action in actions:
        step_snapshot = (
            get_cluster_snapshot_with_clusters(current_cluster_snapshot_id)
            if current_cluster_snapshot_id else None
        )
        step_clusters = step_snapshot.clusters if step_snapshot else []

        command = build_command(action)
        ctx = ExecutionContext(
            current_cluster_snapshot_id=current_cluster_snapshot_id,
            clusters=step_clusters,
            conversation_id=conversation_id,
            conversation_row=conversation_row,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
            reporter=reporter,
        )
        result = await command.execute(ctx)
        current_cluster_snapshot_id = result.cluster_snapshot_id
        accumulated_cost += result.step_cost
        reply_fragments.append(result.reply_fragment)
        if result.axis_concept_id is not None:
            axis_concept_id = result.axis_concept_id
    return current_cluster_snapshot_id, accumulated_cost, reply_fragments, axis_concept_id
