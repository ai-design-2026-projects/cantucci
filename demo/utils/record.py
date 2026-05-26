import json
import logging
from datetime import datetime, timezone

import demo.utils.state as _state

log = logging.getLogger(__name__)


def is_record_mode() -> bool:
    """Return True when CINEPAL_DEMO_MODE=record."""
    return _state.is_record_mode()


def record_turn(
    conversation_id: str,
    user_message: str,
    response: "SendMessageResponse",
    snapshot_dto: "ClusterSnapshotDto",
) -> None:
    """Append a completed turn to the in-memory recording and flush to disk.

    Args:
        conversation_id: Conversation UUID string.
        user_message:    The user message that produced this turn.
        response:        The SendMessageResponse returned to the client.
        snapshot_dto:    Full snapshot DTO for the cluster snapshot referenced in response.
    """
    if _state._RECORDING_PATH is None:
        raise RuntimeError(
            "CINEPAL_DEMO_RECORDING must be set when CINEPAL_DEMO_MODE=record"
        )

    snap_id = str(response.cluster_snapshot_id)
    _state.snapshots[snap_id] = snapshot_dto.model_dump(mode="json")

    turn: dict = {
        "user_message": user_message,
        "assistant": response.message.model_dump(mode="json"),
        "cluster_snapshot_id": snap_id,
        "turn_cost_usd": 0.0,
    }
    _state.record_turns.setdefault(conversation_id, []).append(turn)

    _flush_recording(conversation_id)
    log.info(
        "turn_recorded",
        extra={
            "conversation_id": conversation_id,
            "turns": len(_state.record_turns[conversation_id]),
        },
    )


def _flush_recording(conversation_id: str) -> None:
    """Write the current recording state to disk.

    Args:
        conversation_id: The conversation whose turns are flushed.
    """
    assert _state._RECORDING_PATH is not None
    _state._RECORDING_PATH.parent.mkdir(parents=True, exist_ok=True)

    turns = _state.record_turns.get(conversation_id, [])
    payload = {
        "name": _state._RECORDING_PATH.stem,
        "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
        "conversation_id": conversation_id,
        "turns": turns,
        "snapshots": _state.snapshots,
    }
    _state._RECORDING_PATH.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
