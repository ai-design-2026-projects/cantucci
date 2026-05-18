"""NDJSON stream protocol tests for POST /sessions/{id}/turns.

These tests exercise the wire format independently of the real orchestrator:
a ``FakeOrchestrator`` lets us script progress events, success returns, and
exceptions, then assert how the router translates each into NDJSON lines.

We mount the real sessions router on a throwaway FastAPI app with the fake
orchestrator bound to ``app.state.orchestrator``. This avoids touching the
session-scoped ``client`` fixture used by the smoke tests.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.types import SessionStatus, StepType
from backend.exceptions import SessionNotFound
from backend.orchestrator.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressStep,
)
from backend.routers.dtos import SessionState, TurnResult
from backend.routers.sessions import router as sessions_router


SESSION_ID = uuid4()


def _make_turn_result(session_id: UUID, *, message: str = "ok") -> TurnResult:
    """Build a deterministic ``TurnResult`` for the fake to return."""
    return TurnResult(
        turn_id=uuid4(),
        session_id=session_id,
        turn_number=1,
        user_message="hi",
        assistant_message=message,
        step_type=StepType.show,
        converged=False,
        created_at=datetime.now(timezone.utc),
        ambiguity_meta=None,
    )


def _make_session_state(session_id: UUID) -> SessionState:
    """Build a minimal ``SessionState`` for the pre-stream existence check."""
    now = datetime.now(timezone.utc)
    return SessionState(
        session_id=session_id,
        status=SessionStatus.active,
        max_turns=10,
        created_at=now,
        updated_at=now,
        turns=[],
    )


class FakeOrchestrator:
    """Scriptable orchestrator double.

    - ``known_session_ids`` controls which session IDs ``get_session`` recognises.
    - ``scripted_events`` are emitted via ``progress_cb`` in order before
      either returning ``returns`` or raising ``raises``.
    - ``progress_delay_s`` sleeps briefly between events so the queue
      genuinely interleaves with the consumer (proves thread-safety wiring).
    """

    def __init__(
        self,
        *,
        known_session_ids: set[UUID],
        scripted_events: list[tuple[ProgressStep, str]],
        returns: TurnResult | None = None,
        raises: Exception | None = None,
        progress_delay_s: float = 0.0,
    ) -> None:
        self.known = known_session_ids
        self.scripted = scripted_events
        self.returns = returns
        self.raises = raises
        self.delay = progress_delay_s
        self.received_cb: list[ProgressEvent] = []

    def get_session(self, session_id: UUID) -> SessionState:
        if session_id not in self.known:
            raise SessionNotFound(f"no such session {session_id}")
        return _make_session_state(session_id)

    async def run_turn(
        self,
        session_id: UUID,
        user_message: str,
        progress_cb: ProgressCallback | None = None,
    ) -> TurnResult:
        for step, phase in self.scripted:
            event = ProgressEvent(step=step, phase=phase)  # type: ignore[arg-type]
            if progress_cb is not None:
                progress_cb(event)
                self.received_cb.append(event)
            if self.delay:
                # Hand control back to the event loop so the streaming consumer
                # can drain events between scripted steps — proves the queue
                # genuinely interleaves with the worker.
                await asyncio.sleep(self.delay)
        if self.raises is not None:
            raise self.raises
        assert self.returns is not None
        return self.returns


def _app_with(orchestrator: FakeOrchestrator) -> FastAPI:
    """Build a throwaway FastAPI app that uses the given fake."""
    app = FastAPI()
    app.state.orchestrator = orchestrator
    app.include_router(sessions_router)
    return app


def _stream_post(
    client: TestClient,
    session_id: UUID,
    *,
    message: str = "hi",
) -> tuple[int, str, list[dict[str, Any]]]:
    """POST to the streaming endpoint, return (status, content-type, events)."""
    response = client.post(
        f"/sessions/{session_id}/turns",
        json={"user_message": message},
    )
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200:
        return response.status_code, content_type, []
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    return response.status_code, content_type, events


@pytest.fixture()
def known_session_id() -> UUID:
    return SESSION_ID


def test_success_stream_emits_progress_then_result(known_session_id: UUID) -> None:
    """Scripted progress events appear in order, followed by exactly one result."""
    fake = FakeOrchestrator(
        known_session_ids={known_session_id},
        scripted_events=[
            (ProgressStep.understand, "start"),
            (ProgressStep.understand, "end"),
            (ProgressStep.choose, "start"),
            (ProgressStep.choose, "end"),
            (ProgressStep.finalize, "start"),
            (ProgressStep.finalize, "end"),
        ],
        returns=_make_turn_result(known_session_id),
        progress_delay_s=0.001,
    )
    status, ctype, events = _stream_post(TestClient(_app_with(fake)), known_session_id)

    assert status == 200
    assert ctype.startswith("application/x-ndjson")

    progress = [e for e in events if e["type"] == "progress"]
    terminal = events[-1]

    assert len(progress) == 6
    assert terminal["type"] == "result"
    assert terminal["data"]["session_id"] == str(known_session_id)

    # start/end pair invariant: every step appears exactly twice in start→end order.
    seen_phase: dict[str, str] = {}
    for e in progress:
        step = e["step"]
        prev = seen_phase.get(step)
        if prev is None:
            assert e["phase"] == "start", f"{step} ended before it started"
            seen_phase[step] = "start"
        else:
            assert prev == "start" and e["phase"] == "end"
            seen_phase[step] = "end"
    assert all(v == "end" for v in seen_phase.values())


def test_early_exit_emits_wrap_up_after_understand(known_session_id: UUID) -> None:
    """Early-exit paths close ``understand`` then emit a ``wrap_up`` pair."""
    fake = FakeOrchestrator(
        known_session_ids={known_session_id},
        scripted_events=[
            (ProgressStep.understand, "start"),
            (ProgressStep.understand, "end"),
            (ProgressStep.wrap_up, "start"),
            (ProgressStep.wrap_up, "end"),
        ],
        returns=_make_turn_result(known_session_id, message="wrapped"),
    )
    status, _, events = _stream_post(TestClient(_app_with(fake)), known_session_id)

    assert status == 200
    progress = [(e["step"], e["phase"]) for e in events if e["type"] == "progress"]
    assert progress == [
        ("understand", "start"),
        ("understand", "end"),
        ("wrap_up", "start"),
        ("wrap_up", "end"),
    ]
    assert events[-1]["type"] == "result"


def test_every_line_is_valid_json(known_session_id: UUID) -> None:
    """No partial frames, no trailing garbage — strict NDJSON."""
    fake = FakeOrchestrator(
        known_session_ids={known_session_id},
        scripted_events=[(ProgressStep.understand, "start"), (ProgressStep.understand, "end")],
        returns=_make_turn_result(known_session_id),
    )
    response = TestClient(_app_with(fake)).post(
        f"/sessions/{known_session_id}/turns",
        json={"user_message": "x"},
    )
    assert response.status_code == 200
    assert response.text.endswith("\n")
    for line in response.text.splitlines():
        assert line.strip(), "no blank lines allowed in NDJSON body"
        json.loads(line)  # raises on invalid framing


def test_terminal_event_appears_exactly_once(known_session_id: UUID) -> None:
    """Stream has exactly one result-or-error event, and it is last."""
    fake = FakeOrchestrator(
        known_session_ids={known_session_id},
        scripted_events=[],
        returns=_make_turn_result(known_session_id),
    )
    _, _, events = _stream_post(TestClient(_app_with(fake)), known_session_id)
    terminals = [e for e in events if e["type"] in {"result", "error"}]
    assert len(terminals) == 1
    assert events[-1] is terminals[0]


def test_error_event_replaces_result_when_worker_raises(known_session_id: UUID) -> None:
    """A mid-turn raise becomes a terminal error event, HTTP stays 200."""
    fake = FakeOrchestrator(
        known_session_ids={known_session_id},
        scripted_events=[(ProgressStep.understand, "start")],
        raises=RuntimeError("understand crashed"),
    )
    status, _, events = _stream_post(TestClient(_app_with(fake)), known_session_id)

    assert status == 200
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "RuntimeError"
    assert "understand crashed" in events[-1]["message"]


def test_missing_session_returns_404_before_stream_opens(known_session_id: UUID) -> None:
    """SessionNotFound is rejected pre-stream so the 404 contract is preserved."""
    fake = FakeOrchestrator(
        known_session_ids=set(),  # nothing known
        scripted_events=[],
        returns=_make_turn_result(known_session_id),
    )
    response = TestClient(_app_with(fake)).post(
        f"/sessions/{uuid4()}/turns",
        json={"user_message": "x"},
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_empty_message_returns_422_before_stream_opens(known_session_id: UUID) -> None:
    """Whitespace-only messages are rejected pre-stream by pydantic validation."""
    fake = FakeOrchestrator(
        known_session_ids={known_session_id},
        scripted_events=[],
        returns=_make_turn_result(known_session_id),
    )
    response = TestClient(_app_with(fake)).post(
        f"/sessions/{known_session_id}/turns",
        json={"user_message": "   "},
    )
    assert response.status_code == 422
