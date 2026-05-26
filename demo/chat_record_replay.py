import asyncio
import json
import logging
import os
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_DEMO_MODE: str | None = os.getenv("CINEPAL_DEMO_MODE")
_RECORDING_PATH: Path | None = (
    Path(os.environ["CINEPAL_DEMO_RECORDING"])
    if os.getenv("CINEPAL_DEMO_RECORDING")
    else None
)

# Record-mode state: { conversation_id -> [turn_dict, ...] }
_record_turns: dict[str, list[dict]] = {}
# Shared snapshot store for both modes
_snapshots: dict[str, dict] = {}
# Replay-mode state: { conversation_id -> deque[turn_dict] }
_replay_queues: dict[str, deque[dict]] = {}


def is_record_mode() -> bool:
    """Return True when CINEPAL_DEMO_MODE=record."""
    return _DEMO_MODE == "record"


def is_replay_mode() -> bool:
    """Return True when CINEPAL_DEMO_MODE=replay."""
    return _DEMO_MODE == "replay"


def load_recording(path: Path | None = None) -> None:
    """Load a recording JSON file into the in-memory replay state.

    Must be called before any replay_turn calls. Reads CINEPAL_DEMO_RECORDING
    if path is not supplied.

    Args:
        path: Path to the recording JSON file. Defaults to _RECORDING_PATH.

    Raises:
        FileNotFoundError: If the recording file cannot be found.
        RuntimeError: If CINEPAL_DEMO_RECORDING is unset and path is None.
    """
    global _snapshots
    target = path or _RECORDING_PATH
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
    _snapshots = data.get("snapshots", {})
    turns_list: list[dict] = data.get("turns", [])

    # Build a deque keyed by a sentinel conversation id so any conversation
    # in replay mode shares the same sequential turn queue.
    _replay_queues["__default__"] = deque(turns_list)
    log.info("recording_loaded", extra={"path": str(target), "turns": len(turns_list)})


async def replay_turn(
    conversation_id: uuid.UUID,
    user_message: str,
) -> "SendMessageResponse":
    """Return the next recorded turn response and emit SSE progress events.

    Pops the next turn from the in-memory queue and returns a SendMessageResponse
    built from it. Also appends the assistant message to the DB and emits synthetic
    progress events through the conversation's SSE queue.

    Args:
        conversation_id: The live replay conversation UUID.
        user_message:    The user message text (stored for logging only).

    Returns:
        SendMessageResponse with the recorded assistant message and snapshot id.

    Raises:
        RuntimeError: If the replay queue is empty (too many messages sent).
    """
    from backend.data_access.conversations.queries import append_message
    from backend.agents.coordinator.tools.progress import get_queue
    from backend.routers.dto.conversations.dtos import MessageDto, SendMessageResponse

    queue_key = "__default__"
    turn_queue = _replay_queues.get(queue_key)
    if not turn_queue:
        raise RuntimeError(
            "Replay queue exhausted — more messages sent than turns in the recording."
        )
    turn = turn_queue.popleft()

    msg_id = append_message(conversation_id, "assistant", turn["assistant"]["content"])
    log.info(
        "replay_turn_served",
        extra={"conversation_id": str(conversation_id), "turns_remaining": len(turn_queue)},
    )

    # Emit synthetic progress events so the frontend step indicator animates.
    ssq = get_queue(str(conversation_id))
    if ssq is not None:
        for event in (
            {"type": "step", "step": "intent"},
            {"type": "step", "step": "clustering"},
            {"type": "turn_done"},
        ):
            try:
                ssq.put_nowait(event)
            except asyncio.QueueFull:
                pass

    return SendMessageResponse(
        message=MessageDto(
            id=msg_id,
            role="assistant",
            content=turn["assistant"]["content"],
            created_at=datetime.now(tz=timezone.utc),
            suggestion=turn["assistant"].get("suggestion"),
        ),
        cluster_snapshot_id=uuid.UUID(turn["cluster_snapshot_id"]),
    )


def get_recorded_snapshot(snapshot_id: str) -> "ClusterSnapshotDto | None":
    """Return a ClusterSnapshotDto loaded from the recording, or None if not found.

    Used by the snapshot router in replay mode to serve snapshots without DB access.

    Args:
        snapshot_id: Snapshot UUID string.

    Returns:
        ClusterSnapshotDto parsed from the recording, or None.
    """
    from backend.routers.dto.cluster_snapshots.dtos import ClusterSnapshotDto

    raw = _snapshots.get(str(snapshot_id))
    if raw is None:
        return None
    return ClusterSnapshotDto.model_validate(raw)


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
    if _RECORDING_PATH is None:
        raise RuntimeError(
            "CINEPAL_DEMO_RECORDING must be set when CINEPAL_DEMO_MODE=record"
        )

    snap_id = str(response.cluster_snapshot_id)
    _snapshots[snap_id] = snapshot_dto.model_dump(mode="json")

    turn: dict = {
        "user_message": user_message,
        "assistant": response.message.model_dump(mode="json"),
        "cluster_snapshot_id": snap_id,
        "turn_cost_usd": 0.0,
        "progress_events": [],
    }
    _record_turns.setdefault(conversation_id, []).append(turn)

    _flush_recording(conversation_id)
    log.info(
        "turn_recorded",
        extra={
            "conversation_id": conversation_id,
            "turns": len(_record_turns[conversation_id]),
        },
    )


def _flush_recording(conversation_id: str) -> None:
    """Write the current recording state to disk.

    Args:
        conversation_id: The conversation whose turns are flushed.
    """
    assert _RECORDING_PATH is not None
    _RECORDING_PATH.parent.mkdir(parents=True, exist_ok=True)

    turns = _record_turns.get(conversation_id, [])
    payload = {
        "name": _RECORDING_PATH.stem,
        "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
        "conversation_id": conversation_id,
        "turns": turns,
        "snapshots": _snapshots,
    }
    _RECORDING_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
