from __future__ import annotations

import logging
import uuid

from backend.agents.clarifier.agent import agent as clarifier_agent
from backend.agents.intent.types import IntentAction, IntentResult
from backend.coordinator.commands.factory import build_command
from backend.coordinator.tools.clarification_state import mark_awaiting
from backend.coordinator.tools.progress import ProgressReporter
from backend.coordinator.types import CoordinatorResult, sentinel_cluster_snapshot_id
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.settings import get_settings

log = logging.getLogger(__name__)


async def clarify_if_low_confidence(
    intent: IntentResult,
    clusters: list[ClusterRow],
    user_message: str,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
    current_cluster_snapshot_id: uuid.UUID | None,
    reporter: ProgressReporter,
) -> CoordinatorResult | None:
    """Gate state-changing actions behind a confidence threshold.

    If any state-changing action falls below the configured confidence threshold,
    calls the Clarifier and returns a disambiguation question without modifying
    cluster state.  Returns None to signal that dispatch should proceed normally.

    Args:
        intent:                      Classified intent with one or more actions.
        clusters:                    Current cluster list for the clarifier prompt.
        user_message:                Raw user message.
        conversation_id:             Conversation UUID.
        message_id:                  Current message UUID for LLM logging.
        accumulated_cost:            Running LLM cost before this check.
        current_cluster_snapshot_id: Active cluster snapshot (snapshot is not modified).
        reporter:                    SSE progress reporter for this turn.

    Returns:
        ``CoordinatorResult`` with clarification text, or None to continue dispatch.
    """
    cfg = get_settings()
    low_confidence_action: IntentAction | None = next(
        (
            a for a in intent.actions
            if build_command(a).CREATES_SNAPSHOT
            and a.confidence < cfg.intent.confidence_threshold
        ),
        None,
    )
    if low_confidence_action is None:
        return None

    log.info(
        "coordinator_low_confidence_gate",
        extra={
            "conversation_id": str(conversation_id),
            "navigation_mode": low_confidence_action.mode.value,
            "confidence": low_confidence_action.confidence,
            "threshold": cfg.intent.confidence_threshold,
            "concept": low_confidence_action.concept,
        },
    )
    reporter.step("clarifier")
    clarification = await clarifier_agent.run(
        user_message=user_message,
        clusters=clusters,
        action=low_confidence_action,
        conversation_id=conversation_id,
        message_id=message_id,
        accumulated_cost=accumulated_cost,
    )
    mark_awaiting(conversation_id)
    return CoordinatorResult(
        reply_text=clarification.text,
        cluster_snapshot_id=current_cluster_snapshot_id or sentinel_cluster_snapshot_id(),
    )
