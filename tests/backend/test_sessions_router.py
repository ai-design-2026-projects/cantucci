"""HTTP layer tests for GET /sessions and DELETE /sessions/{id}.

Mounts only the sessions router on a throwaway FastAPI app.
get_current_user is overridden via dependency_overrides.
api_sessions functions are monkeypatched — no real DB needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.sessions as api_sessions_module
from backend.api.sessions import SessionSummaryRow
from backend.auth import User, get_current_user
from backend.routers.sessions import router as sessions_router


_NOW = datetime.now(timezone.utc)
_FAKE_USER = User(id=uuid4(), email="test@example.com", role="user")


def _app(user: User | None = _FAKE_USER) -> FastAPI:
    """Throwaway FastAPI app with the sessions router and injected auth."""
    app = FastAPI()
    app.include_router(sessions_router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _summary(session_id: UUID | None = None) -> SessionSummaryRow:
    return SessionSummaryRow(
        session_id=session_id or uuid4(),
        status="active",
        created_at=_NOW,
        updated_at=_NOW,
        turn_count=3,
    )


# --- GET /sessions ---

def test_list_sessions_returns_401_when_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_sessions_module, "list_sessions_by_user", lambda uid: [])
    response = TestClient(_app(user=None)).get("/sessions/list")
    assert response.status_code == 401


def test_list_sessions_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_sessions_module, "list_sessions_by_user", lambda uid: [])
    response = TestClient(_app()).get("/sessions/list")
    assert response.status_code == 200
    assert response.json() == []


def test_list_sessions_returns_all_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    s1, s2 = _summary(), _summary()
    monkeypatch.setattr(api_sessions_module, "list_sessions_by_user", lambda uid: [s1, s2])
    response = TestClient(_app()).get("/sessions/list")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["session_id"] == str(s1.session_id)
    assert data[1]["session_id"] == str(s2.session_id)
    assert data[0]["turn_count"] == 3


def test_list_sessions_passes_authenticated_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint forwards the JWT user_id, not an arbitrary query param."""
    received: list[uuid.UUID] = []

    def fake_list(uid: uuid.UUID) -> list[SessionSummaryRow]:
        received.append(uid)
        return []

    monkeypatch.setattr(api_sessions_module, "list_sessions_by_user", fake_list)
    TestClient(_app()).get("/sessions/list")
    assert received == [_FAKE_USER.id]


# --- DELETE /sessions/delete/{id} ---

def test_delete_session_returns_401_when_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_sessions_module, "delete_session", lambda sid, uid: True)
    response = TestClient(_app(user=None)).delete(f"/sessions/delete/{uuid4()}")
    assert response.status_code == 401


def test_delete_session_returns_204_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_sessions_module, "delete_session", lambda sid, uid: True)
    response = TestClient(_app()).delete(f"/sessions/delete/{uuid4()}")
    assert response.status_code == 204
    assert response.content == b""


def test_delete_session_returns_404_when_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_sessions_module, "delete_session", lambda sid, uid: False)
    response = TestClient(_app()).delete(f"/sessions/delete/{uuid4()}")
    assert response.status_code == 404


def test_delete_session_passes_correct_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """session_id from the path and user_id from the token reach the API layer."""
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    def fake_delete(sid: uuid.UUID, uid: uuid.UUID) -> bool:
        calls.append((sid, uid))
        return True

    monkeypatch.setattr(api_sessions_module, "delete_session", fake_delete)
    session_id = uuid4()
    TestClient(_app()).delete(f"/sessions/delete/{session_id}")
    assert calls == [(session_id, _FAKE_USER.id)]
