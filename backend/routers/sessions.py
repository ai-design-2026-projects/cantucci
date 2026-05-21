import asyncio
import logging
from contextlib import suppress
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.auth import User, get_current_user
from backend.exceptions import SessionNotFound
from backend.orchestrator.orchestrator import Orchestrator
from backend.routers.dto.sessions.dtos import SessionDto, TurnRequest
from backend.routers.dto.sessions.streaming import (
    ClusterSnapshotEvent,
    ErrorEvent,
    ProgressEvent,
    ResultEvent,
    StreamEvent,
)

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


@router.get("/list", response_model=list[SessionDto])
def list_sessions(
    user: User | None = Depends(get_current_user),
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> list[SessionDto]:
    """List all sessions owned by the authenticated user, newest first.

    Args:
        user:         Resolved by ``get_current_user``; None for anonymous.
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        List of ``SessionDto`` (turns=[]) ordered by updated_at DESC (HTTP 200).

    Raises:
        HTTPException(401): If the request is anonymous.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return orchestrator.list_sessions(user.id)


@router.post("", response_model=SessionDto, status_code=201)
def create_session(
    user: User | None = Depends(get_current_user),
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> SessionDto:
    """Create a new recommendation session.

    Returns an initial ``SessionDto`` with status=active and an empty turn
    list. The session_id in the response is used as the path parameter for
    subsequent turn requests.

    Args:
        user:         Resolved by ``get_current_user``; None for anonymous.
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        The newly created ``SessionDto`` (HTTP 201).
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
    - ``{"type": "result", "data": <TurnDto>}`` emitted once when the turn
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


@router.get("/{session_id}", response_model=SessionDto)
def get_session(
    session_id: UUID,
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> SessionDto:
    """Retrieve full session state including all turns in turn_number order.

    Args:
        session_id:   UUID of the session to retrieve (path parameter).
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        The ``SessionDto`` with all turns (HTTP 200).

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


@router.delete("/delete/{session_id}", status_code=204)
def delete_session(
    session_id: UUID,
    user: User | None = Depends(get_current_user),
    orchestrator: Orchestrator = Depends(_orchestrator),
) -> None:
    """Delete a session and all its child data.

    Only the owning user can delete a session. Both "not found" and "owned by
    someone else" return 404 to avoid disclosing session existence to
    unauthorized callers.

    Active sessions are deletable. If a turn is in flight when the delete
    commits, the in-flight turn will receive a ForeignKeyViolation on its next
    DB write, which surfaces as an ErrorEvent on its NDJSON stream.

    Args:
        session_id:   UUID of the session to delete (path parameter).
        user:         Resolved by ``get_current_user``; None for anonymous callers.
        orchestrator: Injected via ``_orchestrator`` dependency.

    Returns:
        HTTP 204 No Content on success.

    Raises:
        HTTPException(401): If the request is anonymous.
        HTTPException(404): If the session does not exist or is not owned by the caller.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    deleted = orchestrator.delete_session(session_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found.")
    log.debug("DELETE /sessions/{id} user=%s session=%s", user.id, session_id)
