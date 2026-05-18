"""Session and turn HTTP endpoints.

Invariants enforced here:
- No SQL. This layer calls the orchestrator; ``backend/api/`` owns the DB.
- No LLM imports. All model calls happen inside the orchestrator.
- Timestamps are set by the orchestrator (server-side UTC); never read from
  request bodies.
- TODO: add an auth dependency (e.g. X-Oracle-Id header) when auth is designed.
"""

import asyncio
import logging
from contextlib import suppress
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

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
def create_session(orchestrator: Orchestrator = Depends(_orchestrator)) -> SessionState:
    """Create a new recommendation session.

    Returns an initial ``SessionState`` with status=active and an empty turn
    list. The session_id in the response is used as the path parameter for
    subsequent turn requests.

    Args:
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        The newly created ``SessionState`` (HTTP 201).
    """
    log.debug("POST /sessions request received")
    state = orchestrator.create_session()
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
    """Drive ``run_turn`` on the event loop and yield NDJSON lines as events arrive.

    Wiring:
      - The orchestrator runs on the event loop, so ``progress_cb`` is just
        ``queue.put_nowait``. No cross-thread hop, no ``call_soon_threadsafe``.
      - A sentinel object signals "worker is done" so the generator can exit.
      - When the client disconnects, FastAPI cancels this generator; the
        ``finally`` block cancels the worker task. ``CancelledError``
        propagates into every speculative LLM call via the async harness,
        aborting the in-flight ``httpx`` requests instead of letting them
        complete and bill us.

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

    def progress_cb(event: ProgressEvent | ClusterSnapshotEvent) -> None:
        """Push a progress event onto the stream queue. Runs on the event loop."""
        queue.put_nowait(event)

    async def _run_worker() -> None:
        try:
            result = await orchestrator.run_turn(
                session_id,
                user_message,
                progress_cb=progress_cb,
            )
            await queue.put(ResultEvent(data=result))
        except asyncio.CancelledError:
            # Client disconnected: cancellation has already cascaded into every
            # in-flight LLM call. There is nobody to read a terminal event, so
            # just unblock the consumer and let the task end cancelled.
            await queue.put(done)
            raise
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
            # Always unblock the consumer. Two ``done`` sentinels are harmless;
            # the consumer breaks on the first one.
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
        # Client disconnect or stream completion: cancel any still-running
        # worker so its CancelledError cascades into in-flight LLM calls.
        if not worker.done():
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        else:
            # Already finished — surface any unexpected raise that escaped
            # the broad handler.
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
