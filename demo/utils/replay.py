import asyncio
import logging
import uuid
from collections import deque
from pathlib import Path

import demo.utils.state as _state

log = logging.getLogger(__name__)


def _optional_uuid(raw_value: object) -> uuid.UUID | None:
    """Parse optional UUID values from recordings, including legacy string sentinels."""
    if raw_value is None:
        return None
    if isinstance(raw_value, uuid.UUID):
        return raw_value
    if isinstance(raw_value, str):
        value = raw_value.strip()
        if value == "" or value.lower() in {"none", "null"}:
            return None
        return uuid.UUID(value)
    raise TypeError(f"Expected UUID string or null, got {type(raw_value).__name__}")


def is_record_mode() -> bool:
    """Return True when CINEPAL_DEMO_MODE=record."""
    return _state.is_record_mode()


def is_replay_mode() -> bool:
    """Return True when CINEPAL_DEMO_MODE=replay."""
    return _state.is_replay_mode()


def load_recording(path: Path | None = None) -> None:
    """Load a recording JSON file into the in-memory replay state.

    Must be called before any replay_turn calls. Reads CINEPAL_DEMO_RECORDING
    if path is not supplied.

    Args:
        path: Path to the recording JSON file. Defaults to _state._RECORDING_PATH.

    Raises:
        FileNotFoundError: If the recording file cannot be found.
        RuntimeError: If CINEPAL_DEMO_RECORDING is unset and path is None.
    """
    import json

    target = path or _state._RECORDING_PATH
    if target is None:
        raise RuntimeError(
            "CINEPAL_DEMO_RECORDING must be set when CINEPAL_DEMO_MODE=replay"
        )
    if not target.is_file():
        recordings_dir = target.parent
        candidates = sorted(recordings_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise FileNotFoundError(
                f"No recording found at {target} and no fallback in {recordings_dir}."
            )
        target = candidates[-1]
        log.warning("recording file not found; falling back to %s", target.name)

    data = json.loads(target.read_text(encoding="utf-8"))
    _state.replay_turns_template = data.get("turns", [])
    _state.replay_queues = {}
    log.info("recording_loaded", extra={"path": str(target), "turns": len(_state.replay_turns_template)})


async def replay_turn(
    conversation_id: uuid.UUID,
    user_message: str,
) -> "SendMessageResponse":
    """Return the next recorded turn response and emit SSE progress events.

    Pops the next turn from the in-memory queue and returns a SendMessageResponse
    built from it. Also appends the assistant message to the DB and emits synthetic
    progress events through the conversation's SSE queue. Snapshot data is read
    directly from the database (it was persisted during the original recording session).

    Args:
        conversation_id: The live replay conversation UUID.
        user_message:    The user message text (stored for logging only).

    Returns:
        SendMessageResponse with the recorded assistant message and snapshot id.

    Raises:
        RuntimeError: If the replay queue is empty (too many messages sent).
    """
    from backend.data_access.cluster_snapshots.queries import record_conversation_snapshot_ref
    from backend.data_access.conversations.queries import append_message, set_current_cluster_snapshot
    from backend.coordinator.tools.progress import get_queue
    from backend.routers.dto.conversations.dtos import MessageDto, SendMessageResponse

    queue_key = str(conversation_id)
    turn_queue = _state.replay_queues.setdefault(queue_key, deque(_state.replay_turns_template))
    if not turn_queue:
        raise RuntimeError(
            "Replay queue exhausted — more messages sent than turns in the recording."
        )
    turn = turn_queue.popleft()
    snapshot_id = _optional_uuid(turn.get("cluster_snapshot_id"))
    assistant = turn["assistant"]
    axis_concept_id = _optional_uuid(assistant.get("axis_concept_id"))

    msg_id, msg_created_at = append_message(
        conversation_id,
        "assistant",
        assistant["content"],
        cost_usd=float(turn.get("turn_cost_usd") or 0.0),
        suggestion=assistant.get("suggestion"),
        axis_concept_id=axis_concept_id,
    )
    if snapshot_id is not None:
        set_current_cluster_snapshot(conversation_id, snapshot_id)
        record_conversation_snapshot_ref(conversation_id, snapshot_id)
    log.info(
        "replay_turn_served",
        extra={"conversation_id": str(conversation_id), "turns_remaining": len(turn_queue)},
    )

    ssq = get_queue(str(conversation_id))
    if ssq is not None:
        for event, delay in (
            ({"type": "step", "step": "intent"}, _state._REPLAY_STEP_INTENT_DELAY),
            ({"type": "step", "step": "clustering"}, _state._REPLAY_STEP_CLUSTERING_DELAY),
            ({"type": "turn_done"}, 0.0),
        ):
            try:
                ssq.put_nowait(event)
            except asyncio.QueueFull:
                pass
            if delay:
                await asyncio.sleep(delay)

    return SendMessageResponse(
        message=MessageDto(
            id=msg_id,
            role="assistant",
            content=assistant["content"],
            created_at=msg_created_at,
            suggestion=assistant.get("suggestion"),
            axis_concept_id=axis_concept_id,
        ),
        cluster_snapshot_id=snapshot_id,
    )
