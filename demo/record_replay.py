import asyncio
import json
import logging
import os
from collections import deque
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from backend.logging_setup import log_llm_call
from backend.llm.exceptions import ReplayDriftError
from backend.llm.types import LLMResponse
from backend.llm.utils.schema_validation import validate_response

log = logging.getLogger(__name__)

_LLM_MODE: str | None = os.getenv("CINEPAL_LLM_MODE")
_MANIFEST_DIR: Path | None = (
    Path(os.environ["CINEPAL_LLM_MANIFEST"])
    if os.getenv("CINEPAL_LLM_MANIFEST")
    else None
)
_REPLAY_REALTIME: bool = os.getenv("CINEPAL_LLM_REPLAY_REALTIME") == "1"

_replay_queues: dict[str, deque[dict]] = {}


def is_replay_mode() -> bool:
    """Return True when the harness should serve responses from a recorded manifest."""
    return _LLM_MODE == "replay"


def is_record_mode() -> bool:
    """Return True when the harness should append live responses to a manifest."""
    return _LLM_MODE == "record"


def _load_manifest(session_id: str) -> deque[dict]:
    """Load the JSONL manifest for *session_id* into a deque, caching the result.

    The deque is consumed front-to-back during replay.  Call
    ``reset_replay_state(session_id)`` to reload it (e.g. in tests).
    """
    if session_id not in _replay_queues:
        if _MANIFEST_DIR is None:
            raise RuntimeError(
                "CINEPAL_LLM_MANIFEST must be set when CINEPAL_LLM_MODE=replay"
            )
        path = _MANIFEST_DIR / f"{session_id}.jsonl"
        if not path.is_file():
            manifests = sorted(_MANIFEST_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
            if not manifests:
                raise FileNotFoundError(
                    f"Replay manifest not found at {path} and no fallback manifest exists. "
                    "Run CINEPAL_LLM_MODE=record first to generate one."
                )
            path = manifests[-1]
            log.warning("replay manifest=%s not found; falling back to %s", session_id, path.name)
        entries = deque(json.loads(line) for line in path.read_text().splitlines() if line.strip())
        _replay_queues[session_id] = entries
    return _replay_queues[session_id]


async def replay_next(
    *,
    session_id: str,
    step_type: str,
    run_id: str | UUID,
    turn_id: str | UUID,
    seed: int,
    config_hash: str,
    model_and_version: str,
    prompt_hash: str,
    response_schema: type[BaseModel] | None,
) -> LLMResponse:
    """Return the next recorded response from the session manifest.

    Raises ``ReplayDriftError`` if the manifest contains no entry matching
    the incoming ``step_type``.

    Args:
        session_id:        Session whose manifest queue to consume.
        step_type:         Must match an entry in the manifest; searched linearly.
        run_id:            Experiment run identifier for logging.
        turn_id:           Turn identifier for logging.
        seed:              RNG seed from session config.
        config_hash:       SHA-256 prefix of the YAML config in effect.
        model_and_version: Full model string from config.
        prompt_hash:       SHA-256 prefix of the rendered prompt.
        response_schema:   Optional Pydantic model to validate the replayed content.

    Returns:
        An ``LLMResponse`` built from the manifest entry.

    Raises:
        ReplayDriftError: If no manifest entry matches *step_type*.
    """
    queue = _load_manifest(session_id)
    if not queue:
        raise ReplayDriftError(expected="<empty manifest>", got=step_type, session_id=session_id)
    idx = next((i for i, e in enumerate(queue) if e["step_type"] == step_type), None)
    if idx is None:
        raise ReplayDriftError(expected="<no matching entry>", got=step_type, session_id=session_id)
    entry = queue[idx]
    del queue[idx]
    latency_ms: float = entry.get("latency_ms", 0.0)
    if _REPLAY_REALTIME and latency_ms > 0:
        await asyncio.sleep(latency_ms / 1000.0)
    content: str = entry["content"]
    parsed = validate_response(content, response_schema, step_type) if response_schema else None
    log_llm_call(
        log,
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        seed=seed,
        config_hash=config_hash,
        model_and_version=model_and_version,
        prompt_hash=prompt_hash,
        step_type=step_type,
        input_tokens=entry.get("input_tokens", 0),
        output_tokens=entry.get("output_tokens", 0),
        latency_ms=latency_ms,
    )
    return LLMResponse(
        content=content,
        input_tokens=entry.get("input_tokens", 0),
        output_tokens=entry.get("output_tokens", 0),
        latency_ms=latency_ms,
        cost_usd=0.0,
        parsed=parsed,
    )


def record_append(session_id: str, step_type: str, turn_id: str, resp: LLMResponse) -> None:
    """Append a single harness response to the per-session JSONL manifest.

    Args:
        session_id: Session identifier; becomes the manifest filename.
        step_type:  Name of the calling agent step.
        turn_id:    Turn identifier, stored for cross-referencing.
        resp:       The ``LLMResponse`` to persist.

    Raises:
        RuntimeError: If ``CINEPAL_LLM_MANIFEST`` is not set.
    """
    if _MANIFEST_DIR is None:
        raise RuntimeError(
            "CINEPAL_LLM_MANIFEST must be set when CINEPAL_LLM_MODE=record"
        )
    _MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = _MANIFEST_DIR / f"{session_id}.jsonl"
    entry = {
        "step_type": step_type,
        "turn_id": turn_id,
        "content": resp.content,
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
        "latency_ms": resp.latency_ms,
        "cost_usd": resp.cost_usd,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def reset_replay_state(session_id: str) -> None:
    """Evict a session's manifest queue so it reloads on the next replay call.

    Intended for tests that need to replay the same manifest multiple times
    without restarting the process.

    Args:
        session_id: Session whose cached queue should be evicted.
    """
    _replay_queues.pop(session_id, None)
