"""DB-layer unit tests for list_sessions_by_user and delete_session.

Each test creates its own user (unique email via UUID suffix) so tests are
isolated within the shared session-scoped DB — no teardown needed.
"""

from __future__ import annotations

import uuid

import backend.repository.runs as api_runs
import backend.repository.sessions as api_sessions
import backend.repository.users as api_users
from backend.auth import hash_password


def _make_run() -> uuid.UUID:
    """Insert a minimal run row and return its UUID."""
    return api_runs.create_run(
        name="test-run",
        condition="component_test",
        config_snapshot={},
        config_hash="00000000",
        seed=42,
        model_version="test-model",
    )


def _make_user() -> uuid.UUID:
    """Insert a user with a unique email and return its UUID."""
    email = f"test_{uuid.uuid4().hex[:12]}@example.com"
    return api_users.create_user(email, hash_password("password1"), "user")


def _make_session(run_id: uuid.UUID, user_id: uuid.UUID | None = None) -> uuid.UUID:
    return api_sessions.create_session(
        run_id=run_id,
        seed=1,
        config_hash="00000000",
        model_version="test-model",
        user_id=user_id,
    )


def test_list_sessions_by_user_returns_only_owned(mini_catalogue: int) -> None:
    """Sessions from other users are not visible in the listing."""
    run_id = _make_run()
    user_a = _make_user()
    user_b = _make_user()

    _make_session(run_id, user_a)
    _make_session(run_id, user_a)
    _make_session(run_id, user_b)

    rows = api_sessions.list_sessions_by_user(user_a)
    assert len(rows) == 2
    assert all(r.status == "active" for r in rows)


def test_list_sessions_by_user_excludes_anonymous(mini_catalogue: int) -> None:
    """Anonymous sessions (user_id = NULL) never appear in any user's listing."""
    run_id = _make_run()
    user_id = _make_user()

    _make_session(run_id, user_id=None)

    rows = api_sessions.list_sessions_by_user(user_id)
    assert rows == []


def test_list_sessions_by_user_turn_count(mini_catalogue: int) -> None:
    """turn_count reflects the number of turns appended to the session."""
    run_id = _make_run()
    user_id = _make_user()
    session_id = _make_session(run_id, user_id)

    api_sessions.append_turn(session_id, 1, "msg1", "reply1", "show", False)
    api_sessions.append_turn(session_id, 2, "msg2", "reply2", "ask", False)

    rows = api_sessions.list_sessions_by_user(user_id)
    assert len(rows) == 1
    assert rows[0].turn_count == 2
    assert rows[0].first_user_message == "msg1"


def test_list_sessions_by_user_first_message_is_none_for_empty_session(mini_catalogue: int) -> None:
    """first_user_message is None when the session has no turns yet."""
    run_id = _make_run()
    user_id = _make_user()
    _make_session(run_id, user_id)

    rows = api_sessions.list_sessions_by_user(user_id)
    assert len(rows) == 1
    assert rows[0].first_user_message is None


def test_list_sessions_by_user_orders_by_updated_at_desc(mini_catalogue: int) -> None:
    """Appending a turn to a session bumps its updated_at, moving it to the front."""
    run_id = _make_run()
    user_id = _make_user()

    session_a = _make_session(run_id, user_id)
    session_b = _make_session(run_id, user_id)
    api_sessions.append_turn(session_b, 1, "msg", "reply", "ask", False)

    rows = api_sessions.list_sessions_by_user(user_id)
    assert len(rows) == 2
    assert rows[0].session_id == session_b
    assert rows[1].session_id == session_a


def test_delete_session_removes_row_and_cascades(mini_catalogue: int) -> None:
    """Deleting a session removes it from the listing; child turns cascade-delete."""
    run_id = _make_run()
    user_id = _make_user()
    session_id = _make_session(run_id, user_id)
    api_sessions.append_turn(session_id, 1, "msg", "reply", "ask", False)

    deleted = api_sessions.delete_session(session_id, user_id)

    assert deleted is True
    assert api_sessions.list_sessions_by_user(user_id) == []


def test_delete_session_returns_false_for_other_users_session(mini_catalogue: int) -> None:
    """A user cannot delete a session they do not own."""
    run_id = _make_run()
    user_a = _make_user()
    user_b = _make_user()
    session_id = _make_session(run_id, user_a)

    deleted = api_sessions.delete_session(session_id, user_b)

    assert deleted is False
    assert len(api_sessions.list_sessions_by_user(user_a)) == 1


def test_delete_session_returns_false_for_missing_session(mini_catalogue: int) -> None:
    """Attempting to delete a nonexistent UUID returns False without raising."""
    user_id = _make_user()

    deleted = api_sessions.delete_session(uuid.uuid4(), user_id)

    assert deleted is False
