"""No-agents baseline system handler.

Returns the root cluster snapshot on every turn without invoking any LLM
agents. This serves as the lower bound on navigation quality.
"""
import uuid

from backend.baseline.no_agents.pipeline import build_no_agents_trace, get_no_agents_snapshot
from backend.baseline.shared.types import SystemTurnResult
from backend.data_access.conversations.types import ConversationRow


class NoAgentsHandler:
    """Implements the session-driver turn protocol for the no-agents baseline."""

    async def handle_turn(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        conversation_row: ConversationRow,
    ) -> SystemTurnResult:
        """Return the root cluster snapshot without processing the user message.

        Args:
            conversation_id: UUID of the active conversation.
            user_message:    Oracle message (not used by this baseline).
            conversation_row: Current conversation row.

        Returns:
            ``SystemTurnResult`` with the root snapshot ID and a no-agents TurnTrace.
        """
        snapshot_id = get_no_agents_snapshot(conversation_id)
        trace = build_no_agents_trace()
        return SystemTurnResult(
            reply_text="(no-agents baseline: clustering unchanged)",
            cluster_snapshot_id=snapshot_id,
            turn_cost_usd=0.0,
            suggestion=None,
            turn_trace=trace,
        )
