"""System-under-test handler selection and adapters."""
import uuid
from typing import Protocol, runtime_checkable


@runtime_checkable
class SystemHandler(Protocol):
    """Protocol for all system-under-test turn handlers."""

    async def handle_turn(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        conversation_row,
    ):
        """Process one oracle turn and return a SystemTurnResult-compatible object."""
        ...


class _ConversationalHandler:
    """Adapts ``Coordinator.handle_message`` to the session-driver turn protocol."""

    def __init__(self) -> None:
        from backend.coordinator.agent import Coordinator
        self._coordinator = Coordinator()

    async def handle_turn(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        conversation_row,
    ):
        from backend.baseline.shared.types import SystemTurnResult

        result = await self._coordinator.handle_message(
            conversation_id=conversation_id,
            user_message=user_message,
            conversation_row=conversation_row,
        )
        return SystemTurnResult(
            reply_text=result.reply_text,
            suggestion=result.suggestion,
            turn_trace=result.turn_trace,
            turn_cost_usd=result.turn_cost_usd,
            cluster_snapshot_id=result.cluster_snapshot_id,
        )


def select_handler(condition: str) -> SystemHandler:
    """Return the system-under-test handler for the given experimental condition.

    Args:
        condition: One of ``"conversational"``, ``"no_agents"``, ``"monolithic"``.

    Returns:
        An object implementing the ``SystemHandler`` protocol.

    Raises:
        ValueError: If ``condition`` is not a recognised value.
    """
    if condition == "conversational":
        return _ConversationalHandler()
    if condition == "no_agents":
        from backend.baseline.no_agents.runner import NoAgentsHandler
        return NoAgentsHandler()
    if condition == "monolithic":
        from backend.baseline.monolithic.runner import MonolithicHandler
        return MonolithicHandler()
    raise ValueError(f"unknown condition: {condition!r}")
