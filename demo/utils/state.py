import os
from collections import deque
from pathlib import Path

_DEMO_MODE: str | None = os.getenv("CINEPAL_DEMO_MODE")
_RECORDING_PATH: Path | None = (
    Path(os.environ["CINEPAL_DEMO_RECORDING"])
    if os.getenv("CINEPAL_DEMO_RECORDING")
    else None
)

# Seconds the replay backend waits between synthetic SSE progress events.
_REPLAY_STEP_INTENT_DELAY: float = 1.2
_REPLAY_STEP_CLUSTERING_DELAY: float = 2.2

# Record-mode state: { conversation_id -> [turn_dict, ...] }
record_turns: dict[str, list[dict]] = {}
# Shared snapshot store for both modes
snapshots: dict[str, dict] = {}
# Snapshot graph for replay mode (pre-recorded DAG of all conversation snapshots)
snapshot_graph: dict = {}
# Replay-mode immutable turn template loaded from the recording.
replay_turns_template: list[dict] = []
# Replay-mode state: { conversation_id -> deque[turn_dict] }
replay_queues: dict[str, deque[dict]] = {}
# Replay-mode visible graph state: { conversation_id -> [snapshot_id, ...] }
replay_visible_snapshot_ids: dict[str, list[str]] = {}
# Replay-mode DB hydration guard.
persisted_snapshot_ids: set[str] = set()


def is_record_mode() -> bool:
    """Return True when CINEPAL_DEMO_MODE=record."""
    return _DEMO_MODE == "record"


def is_replay_mode() -> bool:
    """Return True when CINEPAL_DEMO_MODE=replay."""
    return _DEMO_MODE == "replay"
