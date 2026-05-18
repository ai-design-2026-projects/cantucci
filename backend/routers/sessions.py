"""Session and turn HTTP endpoints.

Invariants enforced here:
- No SQL. This layer calls the orchestrator; ``backend/api/`` owns the DB.
- No LLM imports. All model calls happen inside the orchestrator.
- Timestamps are set by the orchestrator (server-side UTC); never read from
  request bodies.
"""

import asyncio
import logging
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.auth import User, get_current_user
from backend.exceptions import SessionNotFound
from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.progress import (
    ClusterSnapshotEvent,
    ErrorEvent,
    ProgressEvent,
    ResultEvent,
    StreamEvent,
)
from backend.routers.dtos import SessionState, TurnRequest

log = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _orchestrator(request: Request) -> Orchestrator:
    """Return the app-scoped orchestrator instance bound in app.state.

    The concrete type is set during the lifespan in ``backend/app.py``.
    If app.state.orchestrator is missing an AttributeError surfaces as 500,
    which is the correct loud-failure behaviour.

    Args:
        request: The current FastAPI request (injected by the DI framework).

    Returns:
        The ``Orchestrator`` instance bound to this application.
    """
    return request.app.state.orchestrator  # type: ignore[return-value]


@router.post("", response_model=SessionState, status_code=201)
def create_session(
    orchestrator: Orchestrator = Depends(_orchestrator),
    user: User | None = Depends(get_current_user),
) -> SessionState:
    """Create a new recommendation session.

    Anonymous callers (no ``Authorization`` header) get a session with
    ``user_id=NULL``. Authenticated callers get the session linked to their
    ``user_id``.

    Args:
        orchestrator: Injected via ``_orchestrator`` dependency.
        user:         Resolved by ``get_current_user``; None for anonymous.

    Returns:
        The newly created ``SessionState`` (HTTP 201).
    """
    log.debug("POST /sessions request received")
    state = orchestrator.create_session(user_id=user.id if user else None)
    log.info("session created", extra={"session_id": str(state.session_id)})
    log.debug(
        "POST /sessions response",
        extra={"session_id": str(state.session_id), "max_turns": state.max_turns},
    )
    return state


def _serialize(event: StreamEvent) -> str:
    """Render one stream event as a single NDJSON line (trailing newline)."""
    return event.model_dump_json() + "\n"


async def _turn_event_stream(
    orchestrator: Orchestrator,
    session_id: UUID,
    user_message: str,
) -> AsyncIterator[str]:
    """Run a turn in a worker thread and yield NDJSON lines as events arrive.

    Wiring:
      - An ``asyncio.Queue`` carries events from the worker thread to the
        async generator running on the event loop.
      - ``progress_cb`` is a thread-safe shim: the orchestrator (sync, on a
        thread) calls it; we marshal each event onto the event loop via
        ``loop.call_soon_threadsafe`` so the queue is only touched from the
        loop thread.
      - A sentinel object signals "worker is done" so the generator can exit.

    Failures inside the worker become a single trailing ``ErrorEvent``; the
    HTTP status is already 200 by the time we get here (headers flushed when
    the StreamingResponse started), so an in-band error event is the only
    way to surface the failure to the client.

    Args:
        orchestrator: The app-scoped orchestrator.
        session_id:   UUID of the live session.
        user_message: The oracle's message for this turn.

    Yields:
        One NDJSON line per ``StreamEvent`` (progress events, then exactly
        one terminal ``result`` or ``error`` event).
    """
    queue: asyncio.Queue[StreamEvent | object] = asyncio.Queue()
    done = object()
    loop = asyncio.get_running_loop()

    def progress_cb(event: ProgressEvent | ClusterSnapshotEvent) -> None:
        """Thread-safe hop from the worker thread onto the event loop."""
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            # Loop is closed; client disconnected. Drop the event silently.
            log.debug("progress event dropped after loop closure")

    async def _run_worker() -> None:
        try:
            result = await asyncio.to_thread(
                orchestrator.handle_turn,
                session_id,
                user_message,
                progress_cb=progress_cb,
            )
            await queue.put(ResultEvent(data=result))
        except SessionNotFound as exc:
            # Pre-check below normally catches this; race conditions land here.
            log.warning("session vanished mid-turn", extra={"session_id": str(session_id)})
            await queue.put(ErrorEvent(code="SessionNotFound", message=str(exc)))
        except Exception as exc:  # noqa: BLE001 — converted to in-band error event.
            log.error(
                "turn failed mid-stream",
                exc_info=True,
                extra={"session_id": str(session_id)},
            )
            await queue.put(ErrorEvent(code=type(exc).__name__, message=str(exc)))
        finally:
            await queue.put(done)

    worker = asyncio.create_task(_run_worker())

    try:
        while True:
            event = await queue.get()
            if event is done:
                break
            assert isinstance(event, (ProgressEvent, ClusterSnapshotEvent, ResultEvent, ErrorEvent))
            yield _serialize(event)
    finally:
        # Worker always completes (it puts ``done`` in its finally clause); the
        # await guarantees the task is not garbage-collected mid-flight and
        # surfaces any unexpected raise that escaped the broad handler.
        await worker


@router.post("/{session_id}/turns")
async def add_turn(
    session_id: UUID,
    body: TurnRequest,
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> StreamingResponse:
    """Submit the oracle's message and stream progress + result as NDJSON.

    Response framing: ``application/x-ndjson`` — one JSON object per line.
    Lines are typed via a ``type`` discriminator:

    - ``{"type": "progress", "step": ..., "phase": "start"|"end", "ts": ...}``
      emitted at each orchestrator step boundary.
    - ``{"type": "result", "data": <TurnResult>}`` emitted once when the turn
      completes successfully. Always the terminal line on success.
    - ``{"type": "error", "code": ..., "message": ...}`` emitted once if the
      turn raises after streaming has started. Always the terminal line on
      mid-stream failure. HTTP status remains 200 in this case.

    Pre-stream validation (empty message, missing session) still produces a
    plain JSON error with 422/404 so retry semantics on the client stay simple.

    Args:
        session_id:   UUID of an existing session (path parameter).
        body:         Request body containing ``user_message`` (non-empty).
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        A ``StreamingResponse`` of NDJSON-framed events.

    Raises:
        HTTPException(404): If *session_id* does not identify a live session.
        HTTPException(422): If ``user_message`` is empty or whitespace-only.
    """
    log.debug(
        "POST /sessions/{id}/turns (stream) request received",
        extra={
            "session_id": str(session_id),
            "user_message_len": len(body.user_message),
        },
    )

    # Pre-stream existence check so 404 stays a real 404 instead of a 200 with
    # a trailing error line. Cheap relative to a turn; one extra session read.
    try:
        orchestrator.get_session(session_id)
    except SessionNotFound as exc:
        log.warning("session not found", extra={"session_id": str(session_id)})
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return StreamingResponse(
        _turn_event_stream(orchestrator, session_id, body.user_message),
        media_type="application/x-ndjson",
    )


@router.get("/{session_id}", response_model=SessionState)
def get_session(
    session_id: UUID,
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> SessionState:
    """Retrieve full session state including all turns in turn_number order.

    Args:
        session_id:   UUID of the session to retrieve (path parameter).
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        The ``SessionState`` with all turns (HTTP 200).

    Raises:
        HTTPException(404): If *session_id* does not identify a live session.
    """
    log.debug(
        "GET /sessions/{id} request received",
        extra={"session_id": str(session_id)},
    )
    try:
        state = orchestrator.get_session(session_id)
    except SessionNotFound as exc:
        log.warning("session not found", extra={"session_id": str(session_id)})
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log.debug(
        "GET /sessions/{id} response",
        extra={"session_id": str(session_id), "n_turns": len(state.turns)},
    )
    return state
