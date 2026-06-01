"""Smoke tests for the eval personas endpoint.

Covers:
- GET /eval/personas — 401 (no auth), 403 (non-admin), 200 empty list (admin).
"""
import pytest
from fastapi.testclient import TestClient


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


class TestListPersonas:
    """GET /eval/personas"""

    def test_no_auth_returns_401(self, client: TestClient) -> None:
        """Unauthenticated request is rejected with 401."""
        response = client.get("/eval/personas")
        assert response.status_code == 401

    def test_non_admin_returns_403(self, client: TestClient, auth_header_user: dict) -> None:
        """Authenticated non-admin is rejected with 403."""
        response = client.get("/eval/personas", headers=auth_header_user)
        assert response.status_code == 403

    def test_admin_returns_empty_list(self, client: TestClient, auth_header_admin: dict) -> None:
        """Admin with an empty DB receives an empty list."""
        response = client.get("/eval/personas", headers=auth_header_admin)
        assert response.status_code == 200
        assert response.json() == []
