import os
from collections import deque
from pathlib import Path

import yaml

_DEMO_MODE: str | None = os.getenv("CINEPAL_DEMO_MODE")
_RECORDING_PATH: Path | None = (
    Path(os.environ["CINEPAL_DEMO_RECORDING"])
    if os.getenv("CINEPAL_DEMO_RECORDING")
    else None
)

_DEMO_YAML_PATH = Path(__file__).parent.parent.parent / "configs" / "demo.yaml"
_demo_cfg: dict = {}
if _DEMO_YAML_PATH.exists():
    _demo_cfg = yaml.safe_load(_DEMO_YAML_PATH.read_bytes()).get("backend", {})

_REPLAY_STEP_INTENT_DELAY: float = _demo_cfg.get("replay_step_intent_delay", 1.2)
_REPLAY_STEP_CLUSTERING_DELAY: float = _demo_cfg.get("replay_step_clustering_delay", 2.2)

# Record-mode state: { conversation_id -> [turn_dict, ...] }
record_turns: dict[str, list[dict]] = {}
# Replay-mode immutable turn template loaded from the recording.
replay_turns_template: list[dict] = []
# Replay-mode state: { conversation_id -> deque[turn_dict] }
replay_queues: dict[str, deque[dict]] = {}


def is_record_mode() -> bool:
    """Return True when CINEPAL_DEMO_MODE=record."""
    return _DEMO_MODE == "record"


def is_replay_mode() -> bool:
    """Return True when CINEPAL_DEMO_MODE=replay."""
    return _DEMO_MODE == "replay"
