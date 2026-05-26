import asyncio
import json
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import demo.utils.state as _state

log = logging.getLogger(__name__)


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
    _state.snapshots = data.get("snapshots", {})
    _state.snapshot_graph = data.get("snapshot_graph", {})
    _state.replay_turns_template = data.get("turns", [])
    _state.replay_queues = {}
    _state.replay_visible_snapshot_ids = {}
    _state.persisted_snapshot_ids = set()
    log.info("recording_loaded", extra={"path": str(target), "turns": len(_state.replay_turns_template)})


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
    from backend.data_access.cluster_snapshots.queries import record_conversation_snapshot_ref
    from backend.data_access.conversations.queries import append_message, set_current_cluster_snapshot
    from backend.agents.coordinator.tools.progress import get_queue
    from backend.routers.dto.conversations.dtos import MessageDto, SendMessageResponse

    queue_key = str(conversation_id)
    turn_queue = _state.replay_queues.setdefault(queue_key, deque(_state.replay_turns_template))
    if not turn_queue:
        raise RuntimeError(
            "Replay queue exhausted — more messages sent than turns in the recording."
        )
    turn = turn_queue.popleft()
    snapshot_id = uuid.UUID(turn["cluster_snapshot_id"])
    _ensure_recorded_snapshot_persisted(snapshot_id)

    msg_id = append_message(conversation_id, "assistant", turn["assistant"]["content"])
    set_current_cluster_snapshot(conversation_id, snapshot_id)
    record_conversation_snapshot_ref(conversation_id, snapshot_id)
    visible_ids = _state.replay_visible_snapshot_ids.setdefault(str(conversation_id), [])
    if str(snapshot_id) not in visible_ids:
        visible_ids.append(str(snapshot_id))
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
            content=turn["assistant"]["content"],
            created_at=datetime.now(tz=timezone.utc),
            suggestion=turn["assistant"].get("suggestion"),
        ),
        cluster_snapshot_id=snapshot_id,
    )


def _ensure_recorded_snapshot_persisted(snapshot_id: uuid.UUID) -> None:
    """Insert minimal DB rows for a recorded snapshot if replay references it.

    Replay serves the rich snapshot payload directly from JSON, but
    ``conversation_snapshot_refs`` has a foreign key to ``cluster_snapshots``.
    Hydrating the recorded IDs keeps that relational bookkeeping intact without
    rerunning clustering or LLM work.
    """
    from backend.data_access.connection import transaction

    snapshot_key = str(snapshot_id)
    if snapshot_key in _state.persisted_snapshot_ids:
        return

    raw = _state.snapshots.get(snapshot_key)
    if raw is None:
        raw = _get_snapshot_graph_node(snapshot_key)
    if raw is None:
        raise RuntimeError(f"Recorded snapshot {snapshot_key} is missing from the recording.")

    parent_id = raw.get("parent_id")
    if parent_id and (_state.snapshots.get(str(parent_id)) or _get_snapshot_graph_node(str(parent_id))):
        _ensure_recorded_snapshot_persisted(uuid.UUID(str(parent_id)))
    else:
        parent_id = None

    params = raw.get("params") or {}
    config_hash = raw.get("config_hash") or "demo-replay"

    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO cluster_snapshots (id, parent_id, operation, params, config_hash, created_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, COALESCE(%s::timestamptz, NOW()))
            ON CONFLICT DO NOTHING
            """,
            (
                snapshot_id,
                uuid.UUID(str(parent_id)) if parent_id else None,
                raw.get("operation") or "demo_replay",
                json.dumps(params),
                config_hash,
                raw.get("created_at"),
            ),
        )

        existing = conn.execute(
            "SELECT id FROM cluster_snapshots WHERE id = %s",
            (snapshot_id,),
        ).fetchone()
        if existing is None:
            raise RuntimeError(
                f"Could not hydrate recorded snapshot {snapshot_key}; a different "
                "snapshot likely already exists with the same cache key."
            )

        for cluster in raw.get("clusters", []):
            cluster_id = uuid.UUID(str(cluster["id"]))
            parent_cluster_id = cluster.get("parent_cluster_id")
            if parent_cluster_id:
                parent_exists = conn.execute(
                    "SELECT id FROM clusters WHERE id = %s",
                    (uuid.UUID(str(parent_cluster_id)),),
                ).fetchone()
                if parent_exists is None:
                    parent_cluster_id = None

            conn.execute(
                """
                INSERT INTO clusters (
                    id,
                    cluster_snapshot_id,
                    label,
                    summary,
                    exemplar_movie_ids,
                    parent_cluster_id
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    cluster_id,
                    snapshot_id,
                    cluster.get("label"),
                    cluster.get("summary"),
                    json.dumps(cluster.get("exemplar_movie_ids") or []),
                    uuid.UUID(str(parent_cluster_id)) if parent_cluster_id else None,
                ),
            )

        for member in raw.get("members", []):
            conn.execute(
                """
                INSERT INTO cluster_memberships (cluster_id, movie_id, probability)
                SELECT %s, %s, %s
                WHERE EXISTS (SELECT 1 FROM movies WHERE id = %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    uuid.UUID(str(member["cluster_id"])),
                    member["movie_id"],
                    member["probability"],
                    member["movie_id"],
                ),
            )

    _state.persisted_snapshot_ids.add(snapshot_key)


def _get_snapshot_graph_node(snapshot_id: str) -> dict | None:
    """Return a graph node by id from the loaded recording, if present."""
    for node in _state.snapshot_graph.get("cluster_snapshots", []):
        if str(node.get("id")) == snapshot_id:
            return node
    return None


def get_recorded_snapshot(snapshot_id: str) -> "ClusterSnapshotDto | None":
    """Return a ClusterSnapshotDto loaded from the recording, or None if not found.

    Used by the snapshot router in replay mode to serve snapshots without DB access.

    Args:
        snapshot_id: Snapshot UUID string.

    Returns:
        ClusterSnapshotDto parsed from the recording, or None.
    """
    from backend.routers.dto.cluster_snapshots.dtos import ClusterSnapshotDto

    raw = _state.snapshots.get(str(snapshot_id))
    if raw is None:
        return None
    return ClusterSnapshotDto.model_validate(raw)


def get_recorded_snapshot_graph(conversation_id: str) -> "ClusterSnapshotGraphDto | None":
    """Return the replay-visible snapshot graph DTO for a conversation.

    The recording stores the full DAG, but replay should reveal only snapshots
    whose turns have already been served to the live conversation. This keeps the
    Evolution Map aligned with the state visible after each replayed message.

    Args:
        conversation_id: Live replay conversation UUID.

    Returns:
        ``ClusterSnapshotGraphDto`` parsed from the recording, or None if no
        snapshot graph was captured in this recording.
    """
    from backend.routers.dto.cluster_snapshots.dtos import ClusterSnapshotGraphDto

    if not _state.snapshot_graph:
        return None

    visible_ids = set(_state.replay_visible_snapshot_ids.get(conversation_id, []))
    if not visible_ids:
        return ClusterSnapshotGraphDto(cluster_snapshots=[])

    visible_graph = {
        **_state.snapshot_graph,
        "cluster_snapshots": [
            node
            for node in _state.snapshot_graph.get("cluster_snapshots", [])
            if str(node.get("id")) in visible_ids
        ],
    }
    return ClusterSnapshotGraphDto.model_validate(visible_graph)
