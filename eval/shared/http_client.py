"""Async HTTP client for the CinePal API.

Wraps the three endpoints an Oracle needs: create a session, submit a turn
(consuming the NDJSON stream), and fetch the full session state.  Parsing
uses the same Pydantic types the backend defines so the client is always
in sync with the server contract.

This is the only layer that touches network I/O in the eval package.  It
never retries — eval failures must surface loudly (CLAUDE.md convention).
"""

import json
import logging
from typing import AsyncIterator
from uuid import UUID

import httpx
from pydantic import TypeAdapter

from backend.orchestrator.turn.progress import (
    ClusterSnapshotEvent,
    ErrorEvent,
    ProgressEvent,
    ResultEvent,
    StreamEvent,
)
from backend.routers.dto.sessions.dtos import SessionDto

log = logging.getLogger(__name__)

_STREAM_EVENT_ADAPTER: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)


class CinePalClient:
    """Async HTTP client that drives the CinePal API on behalf of the Oracle.

    Attributes:
        base_url:    Base URL of the running CinePal backend (e.g. ``"http://localhost:8000"``).
        auth_token:  Bearer token for the ``Authorization`` header, or ``None`` for anonymous.
    """

    def __init__(self, base_url: str, auth_token: str | None = None) -> None:
        """Initialise the client.

        Args:
            base_url:   Base URL of the CinePal backend.
            auth_token: Optional JWT bearer token.
        """
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
        )

    async def create_session(self) -> SessionDto:
        """Create a new CinePal session.

        Returns:
            ``SessionDto`` for the freshly created session.

        Raises:
            httpx.HTTPStatusError: On non-2xx response.
        """
        response = await self._client.post("/sessions")
        response.raise_for_status()
        dto = SessionDto.model_validate_json(response.content)
        log.info("eval session created session_id=%s", dto.session_id)
        return dto

    async def stream_turn(
        self,
        session_id: UUID,
        user_message: str,
    ) -> AsyncIterator[StreamEvent]:
        """Submit the oracle's message and yield NDJSON stream events as they arrive.

        Parses each line as a discriminated ``StreamEvent``.  Yields every
        event in arrival order; the caller is responsible for distinguishing
        terminal ``ResultEvent`` / ``ErrorEvent`` from intermediate ``ProgressEvent``
        and ``ClusterSnapshotEvent``.

        Args:
            session_id:   Session to post the turn to.
            user_message: Oracle's free-text reply for this turn.

        Yields:
            One ``StreamEvent`` per NDJSON line.

        Raises:
            httpx.HTTPStatusError: On non-2xx pre-stream HTTP status (404, 422).
            ValueError: If a line cannot be parsed as a known ``StreamEvent`` type.
        """
        payload = json.dumps({"user_message": user_message})
        async with self._client.stream(
            "POST",
            f"/sessions/{session_id}/turns",
            content=payload,
            headers={"Content-Type": "application/json"},
        ) as response:
            response.raise_for_status()
            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if not line:
                    continue
                event = _STREAM_EVENT_ADAPTER.validate_json(line)
                log.debug(
                    "eval stream event type=%s session_id=%s",
                    event.type,
                    session_id,
                )
                yield event

    async def get_session(self, session_id: UUID) -> SessionDto:
        """Fetch the full session state including all turns.

        Args:
            session_id: UUID of the session to retrieve.

        Returns:
            ``SessionDto`` with all turns in ascending ``turn_number`` order.

        Raises:
            httpx.HTTPStatusError: On non-2xx response.
        """
        response = await self._client.get(f"/sessions/{session_id}")
        response.raise_for_status()
        return SessionDto.model_validate_json(response.content)

    async def aclose(self) -> None:
        """Close the underlying ``httpx`` connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> "CinePalClient":
        """Support use as an async context manager."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the client on context manager exit."""
        await self.aclose()
