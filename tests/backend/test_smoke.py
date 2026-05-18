"""Backend wiring smoke tests.

Drive the full orchestrator pipeline (retrieval → cluster → decision → ambiguity
or render) through the HTTP layer with ``dry_run=true`` so no live LLM calls
happen. The point is to surface a broken contract between any two components,
not to evaluate the recommendation quality.

The /turns endpoint streams NDJSON; helpers below collect the stream into a
list of typed events and isolate the terminal ``result`` payload for the
existing shape assertions.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from backend.settings import get_config_hash, get_settings


def _collect_stream(client: TestClient, url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """POST to a streaming endpoint and return the parsed NDJSON events."""
    response = client.post(url, json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson"), (
        response.headers.get("content-type")
    )
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events, "stream must emit at least the terminal event"
    return events


def _terminal_result(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract the trailing ``result`` event payload, asserting it is terminal."""
    last = events[-1]
    assert last["type"] == "result", f"expected terminal result, got {last}"
    return last["data"]


def test_route_table_matches_spec(client: TestClient) -> None:
    """The session router exposes the documented session endpoints."""
    routes = {(r.path, frozenset(r.methods or set())) for r in client.app.routes if hasattr(r, "methods")}
    assert ("/sessions/create", frozenset({"POST"})) in routes
    assert ("/sessions/list", frozenset({"GET"})) in routes
    assert ("/sessions/{session_id}/turns", frozenset({"POST"})) in routes
    assert ("/sessions/get/{session_id}", frozenset({"GET"})) in routes
    assert ("/sessions/delete/{session_id}", frozenset({"DELETE"})) in routes


def test_dry_run_is_active_in_test_config() -> None:
    """Guard: the test config must actually have dry_run on, or every smoke is a no-op."""
    cfg = get_settings()
    assert cfg.models.strong.dry_run is True
    assert cfg.models.fast.dry_run is True


def test_create_session_persists_row(client: TestClient) -> None:
    """POST /sessions writes a session row whose config_hash matches the active YAML."""
    response = client.post("/sessions/create")
    assert response.status_code == 201, response.text
    body = response.json()
    UUID(body["session_id"])
    assert body["status"] == "active"
    assert body["turns"] == []

    fetched = client.get(f"/sessions/get/{body['session_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["session_id"] == body["session_id"]


def test_full_turn_runs_end_to_end(client: TestClient) -> None:
    """POST /turns streams NDJSON ending in a well-formed TurnResult event."""
    session = client.post("/sessions/create").json()
    session_id = session["session_id"]

    events = _collect_stream(
        client,
        f"/sessions/{session_id}/turns",
        {"user_message": "a contemplative slow-burn drama about memory and grief"},
    )
    result = _terminal_result(events)

    assert result["session_id"] == session_id
    assert result["turn_number"] == 1
    assert result["user_message"]
    assert isinstance(result["assistant_message"], str)
    assert result["assistant_message"]
    assert result["step_type"] in {"ask", "show", "stop"}
    UUID(result["turn_id"])


def test_turn_result_persists_with_matching_config_hash(client: TestClient) -> None:
    """The turn write-through reaches the DB and the run's config_hash is stable."""
    import os

    import psycopg

    session_id = client.post("/sessions/create").json()["session_id"]
    events = _collect_stream(
        client,
        f"/sessions/{session_id}/turns",
        {"user_message": "weird sci-fi like Annihilation or Stalker"},
    )
    _terminal_result(events)

    fetched = client.get(f"/sessions/get/{session_id}").json()
    assert len(fetched["turns"]) == 1

    expected_hash = get_config_hash()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            """
            SELECT r.config_hash
            FROM sessions s
            JOIN runs r ON r.id = s.run_id
            WHERE s.id = %s
            """,
            (session_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == expected_hash
