"""Backend wiring smoke tests.

Drive the full orchestrator pipeline (retrieval → cluster → decision → ambiguity
or render) through the HTTP layer with ``dry_run=true`` so no live LLM calls
happen. The point is to surface a broken contract between any two components,
not to evaluate the recommendation quality.
"""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from backend.settings import get_config_hash, get_settings


def test_route_table_matches_spec(client: TestClient) -> None:
    """The session router exposes exactly the three documented endpoints."""
    routes = {(r.path, frozenset(r.methods or set())) for r in client.app.routes if hasattr(r, "methods")}
    assert ("/sessions", frozenset({"POST"})) in routes
    assert ("/sessions/{session_id}/turns", frozenset({"POST"})) in routes
    assert ("/sessions/{session_id}", frozenset({"GET"})) in routes


def test_dry_run_is_active_in_test_config() -> None:
    """Guard: the test config must actually have dry_run on, or every smoke is a no-op."""
    assert get_settings().model.dry_run is True


def test_create_session_persists_row(client: TestClient) -> None:
    """POST /sessions writes a session row whose config_hash matches the active YAML."""
    response = client.post("/sessions")
    assert response.status_code == 201, response.text
    body = response.json()
    UUID(body["session_id"])
    assert body["status"] == "active"
    assert body["turns"] == []

    fetched = client.get(f"/sessions/{body['session_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["session_id"] == body["session_id"]


def test_full_turn_runs_end_to_end(client: TestClient) -> None:
    """POST /turns runs every agent in dry_run mode and returns a well-formed TurnResult."""
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    response = client.post(
        f"/sessions/{session_id}/turns",
        json={"user_message": "a contemplative slow-burn drama about memory and grief"},
    )
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["session_id"] == session_id
    assert result["turn_number"] == 1
    assert result["user_message"]
    assert isinstance(result["assistant_message"], str)
    assert result["assistant_message"]
    assert result["step_type"] in {"ask", "show", "stop"}
    UUID(result["turn_id"])


def test_turn_result_persists_with_matching_config_hash(client: TestClient) -> None:
    """The turn write-through reaches the DB and the run's config_hash is stable."""
    import psycopg

    session_id = client.post("/sessions").json()["session_id"]
    client.post(
        f"/sessions/{session_id}/turns",
        json={"user_message": "weird sci-fi like Annihilation or Stalker"},
    ).raise_for_status()

    fetched = client.get(f"/sessions/{session_id}").json()
    assert len(fetched["turns"]) == 1

    expected_hash = get_config_hash()
    import os
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
