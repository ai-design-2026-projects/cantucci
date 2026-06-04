"""Smoke tests for the conversations endpoints.

Covers:
- POST /conversations          — 201, anonymous allowed, returns ConversationDto with empty messages.
- GET /conversations/{id}      — 200 with messages=[] on a freshly created conversation (exercises
                                 the fixed ``limit`` query parameter).
- GET /conversations/{random}  — 404 for a non-existent conversation.
- GET /conversations           — 401 when unauthenticated.
- DELETE /conversations/{id}   — 401 when unauthenticated.
"""
import uuid

import pytest
from fastapi.testclient import TestClient


_UNKNOWN = uuid.uuid4()


class TestCreateConversation:
    """POST /conversations"""

    def test_anonymous_create_returns_201(self, client: TestClient) -> None:
        """An anonymous (unauthenticated) POST creates a conversation and returns 201."""
        response = client.post("/conversations")
        assert response.status_code == 201

    def test_create_returns_conversation_dto_fields(self, client: TestClient) -> None:
        """The created conversation has the expected top-level fields."""
        response = client.post("/conversations")
        assert response.status_code == 201
        body = response.json()
        assert "id" in body
        assert "messages" in body
        assert body["messages"] == []

    def test_authenticated_create_also_returns_201(self, client: TestClient, user_token: str) -> None:
        """An authenticated user can also create a conversation."""
        response = client.post(
            "/conversations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 201


class TestGetConversation:
    """GET /conversations/{conversation_id}"""

    def test_unknown_id_returns_404(self, client: TestClient) -> None:
        """A GET request for a non-existent conversation ID returns 404."""
        response = client.get(f"/conversations/{_UNKNOWN}")
        assert response.status_code == 404

    def test_fresh_conversation_returns_empty_messages(self, client: TestClient) -> None:
        """A freshly created conversation returns 200 with messages=[] (validates the limit fix)."""
        create_resp = client.post("/conversations")
        assert create_resp.status_code == 201
        conversation_id = create_resp.json()["id"]

        get_resp = client.get(f"/conversations/{conversation_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["messages"] == []

    def test_limit_zero_is_accepted(self, client: TestClient) -> None:
        """limit=0 is accepted and treated as the default (20), returning 200."""
        create_resp = client.post("/conversations")
        conversation_id = create_resp.json()["id"]
        response = client.get(f"/conversations/{conversation_id}?limit=0")
        assert response.status_code == 200

    def test_explicit_limit_is_accepted(self, client: TestClient) -> None:
        """An explicit limit query param is accepted without error."""
        create_resp = client.post("/conversations")
        conversation_id = create_resp.json()["id"]
        response = client.get(f"/conversations/{conversation_id}?limit=5")
        assert response.status_code == 200


class TestListConversations:
    """GET /conversations"""

    def test_no_auth_returns_401(self, client: TestClient) -> None:
        """An unauthenticated GET /conversations returns 401."""
        response = client.get("/conversations")
        assert response.status_code == 401


class TestDeleteConversation:
    """DELETE /conversations/{conversation_id}"""

    def test_no_auth_returns_401(self, client: TestClient) -> None:
        """An unauthenticated DELETE returns 401."""
        response = client.delete(f"/conversations/{_UNKNOWN}")
        assert response.status_code == 401
