"""Smoke tests for the eval sessions endpoint.

Covers:
- GET /eval/sessions/{session_id} — 401, 403, 404 (unknown UUID).

Also verifies the renamed path parameter ``{session_id}`` (previously
``{eval_session_id}``) is correctly registered in the router.
"""
import uuid

import pytest
from fastapi.testclient import TestClient


_UNKNOWN = uuid.uuid4()


@pytest.fixture()
def auth_header_admin(admin_token: str) -> dict[str, str]:
    """Return Authorization header dict for an admin user.

    Args:
        admin_token: Signed JWT from the ``admin_token`` fixture.

    Returns:
        Dict suitable for passing as ``headers=`` to the test client.
    """
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def auth_header_user(user_token: str) -> dict[str, str]:
    """Return Authorization header dict for a regular user.

    Args:
        user_token: Signed JWT from the ``user_token`` fixture.

    Returns:
        Dict suitable for passing as ``headers=`` to the test client.
    """
    return {"Authorization": f"Bearer {user_token}"}


class TestGetSession:
    """GET /eval/sessions/{session_id}"""

    def test_no_auth_returns_401(self, client: TestClient) -> None:
        """Unauthenticated request is rejected with 401."""
        response = client.get(f"/eval/sessions/{_UNKNOWN}")
        assert response.status_code == 401

    def test_non_admin_returns_403(self, client: TestClient, auth_header_user: dict) -> None:
        """Authenticated non-admin is rejected with 403."""
        response = client.get(f"/eval/sessions/{_UNKNOWN}", headers=auth_header_user)
        assert response.status_code == 403

    def test_unknown_id_returns_404(self, client: TestClient, auth_header_admin: dict) -> None:
        """Admin requesting a non-existent session receives 404."""
        response = client.get(f"/eval/sessions/{_UNKNOWN}", headers=auth_header_admin)
        assert response.status_code == 404

    def test_404_detail_mentions_session(self, client: TestClient, auth_header_admin: dict) -> None:
        """The 404 error body includes 'eval session' to identify the resource type."""
        response = client.get(f"/eval/sessions/{_UNKNOWN}", headers=auth_header_admin)
        assert response.status_code == 404
        assert "eval session" in response.json()["detail"]
