"""HTTP layer tests for GET /sessions and DELETE /sessions/{id}.

Mounts only the sessions router on a throwaway FastAPI app.
get_current_user is overridden via dependency_overrides.
Orchestrator methods are monkeypatched — no real DB needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestrator.domain import SessionStatus
from backend.auth import User, get_current_user
from backend.orchestrator.orchestrator import Orchestrator
from backend.routers.dtos import SessionDto
from backend.routers.sessions import router as sessions_router


_NOW = datetime.now(timezone.utc)
_FAKE_USER = User(id=uuid4(), email="test@example.com", role="user")


def _app(user: User | None = _FAKE_USER, orchestrator: Orchestrator | None = None) -> FastAPI:
    """Throwaway FastAPI app with the sessions router and injected auth + orchestrator."""
    app = FastAPI()
    app.include_router(sessions_router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.state.orchestrator = orchestrator if orchestrator is not None else MagicMock(spec=Orchestrator)
    return app


def _dto(session_id: UUID | None = None, first_user_message: str | None = None) -> SessionDto:
    return SessionDto(
        session_id=session_id or uuid4(),
        status=SessionStatus.active,
        max_turns=10,
        created_at=_NOW,
        updated_at=_NOW,
        turn_count=3,
        first_user_message=first_user_message,
    )


# --- GET /sessions/list ---

def test_list_sessions_returns_401_when_anonymous() -> None:
    response = TestClient(_app(user=None)).get("/sessions/list")
    assert response.status_code == 401


def test_list_sessions_returns_empty_list() -> None:
    orc = MagicMock(spec=Orchestrator)
    orc.list_sessions.return_value = []
    response = TestClient(_app(orchestrator=orc)).get("/sessions/list")
    assert response.status_code == 200
    assert response.json() == []


def test_list_sessions_returns_all_summaries() -> None:
    s1 = _dto(first_user_message="Hello there")
    s2 = _dto(first_user_message=None)
    orc = MagicMock(spec=Orchestrator)
    orc.list_sessions.return_value = [s1, s2]
    response = TestClient(_app(orchestrator=orc)).get("/sessions/list")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["session_id"] == str(s1.session_id)
    assert data[1]["session_id"] == str(s2.session_id)
    assert data[0]["turn_count"] == 3
    assert data[0]["first_user_message"] == "Hello there"
    assert data[1]["first_user_message"] is None


def test_list_sessions_passes_authenticated_user_id() -> None:
    """The endpoint forwards the JWT user_id to the orchestrator."""
    orc = MagicMock(spec=Orchestrator)
    orc.list_sessions.return_value = []
    TestClient(_app(orchestrator=orc)).get("/sessions/list")
    orc.list_sessions.assert_called_once_with(_FAKE_USER.id)


# --- DELETE /sessions/delete/{id} ---

def test_delete_session_returns_401_when_anonymous() -> None:
    response = TestClient(_app(user=None)).delete(f"/sessions/delete/{uuid4()}")
    assert response.status_code == 401


def test_delete_session_returns_204_on_success() -> None:
    orc = MagicMock(spec=Orchestrator)
    orc.delete_session.return_value = True
    response = TestClient(_app(orchestrator=orc)).delete(f"/sessions/delete/{uuid4()}")
    assert response.status_code == 204
    assert response.content == b""


def test_delete_session_returns_404_when_not_found() -> None:
    orc = MagicMock(spec=Orchestrator)
    orc.delete_session.return_value = False
    response = TestClient(_app(orchestrator=orc)).delete(f"/sessions/delete/{uuid4()}")
    assert response.status_code == 404


def test_delete_session_passes_correct_ids() -> None:
    """session_id from the path and user_id from the token reach the orchestrator."""
    orc = MagicMock(spec=Orchestrator)
    orc.delete_session.return_value = True
    session_id = uuid4()
    TestClient(_app(orchestrator=orc)).delete(f"/sessions/delete/{session_id}")
    orc.delete_session.assert_called_once_with(session_id, _FAKE_USER.id)
