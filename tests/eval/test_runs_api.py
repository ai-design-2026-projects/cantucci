"""Smoke tests for the eval runs endpoints.

Covers:
- GET /eval/runs        — 401 (no auth), 403 (non-admin), 200 empty list (admin).
- GET /eval/runs/{id}   — 401, 403, 404 (unknown UUID).
- GET /eval/runs/{id}/aggregate — 401, 403, 404.
- GET /eval/runs/{id}/sessions  — 401, 403, 200 empty list (unknown run returns []).
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


class TestListRuns:
    """GET /eval/runs"""

    def test_no_auth_returns_401(self, client: TestClient) -> None:
        """Unauthenticated request is rejected with 401."""
        response = client.get("/eval/runs")
        assert response.status_code == 401

    def test_non_admin_returns_403(self, client: TestClient, auth_header_user: dict) -> None:
        """Authenticated non-admin is rejected with 403."""
        response = client.get("/eval/runs", headers=auth_header_user)
        assert response.status_code == 403

    def test_admin_returns_empty_list(self, client: TestClient, auth_header_admin: dict) -> None:
        """Admin with an empty DB receives an empty list."""
        response = client.get("/eval/runs", headers=auth_header_admin)
        assert response.status_code == 200
        assert response.json() == []

    def test_admin_pagination_params_accepted(self, client: TestClient, auth_header_admin: dict) -> None:
        """limit and offset query params are accepted without error."""
        response = client.get("/eval/runs?limit=10&offset=0", headers=auth_header_admin)
        assert response.status_code == 200


class TestGetRun:
    """GET /eval/runs/{run_id}"""

    def test_no_auth_returns_401(self, client: TestClient) -> None:
        """Unauthenticated request is rejected with 401."""
        response = client.get(f"/eval/runs/{_UNKNOWN}")
        assert response.status_code == 401

    def test_non_admin_returns_403(self, client: TestClient, auth_header_user: dict) -> None:
        """Authenticated non-admin is rejected with 403."""
        response = client.get(f"/eval/runs/{_UNKNOWN}", headers=auth_header_user)
        assert response.status_code == 403

    def test_unknown_id_returns_404(self, client: TestClient, auth_header_admin: dict) -> None:
        """Admin requesting a non-existent run receives 404."""
        response = client.get(f"/eval/runs/{_UNKNOWN}", headers=auth_header_admin)
        assert response.status_code == 404


class TestGetRunAggregate:
    """GET /eval/runs/{run_id}/aggregate"""

    def test_no_auth_returns_401(self, client: TestClient) -> None:
        """Unauthenticated request is rejected with 401."""
        response = client.get(f"/eval/runs/{_UNKNOWN}/aggregate")
        assert response.status_code == 401

    def test_non_admin_returns_403(self, client: TestClient, auth_header_user: dict) -> None:
        """Authenticated non-admin is rejected with 403."""
        response = client.get(f"/eval/runs/{_UNKNOWN}/aggregate", headers=auth_header_user)
        assert response.status_code == 403

    def test_unknown_id_returns_404(self, client: TestClient, auth_header_admin: dict) -> None:
        """Admin requesting aggregate for a non-existent run receives 404."""
        response = client.get(f"/eval/runs/{_UNKNOWN}/aggregate", headers=auth_header_admin)
        assert response.status_code == 404


class TestListRunSessions:
    """GET /eval/runs/{run_id}/sessions"""

    def test_no_auth_returns_401(self, client: TestClient) -> None:
        """Unauthenticated request is rejected with 401."""
        response = client.get(f"/eval/runs/{_UNKNOWN}/sessions")
        assert response.status_code == 401

    def test_non_admin_returns_403(self, client: TestClient, auth_header_user: dict) -> None:
        """Authenticated non-admin is rejected with 403."""
        response = client.get(f"/eval/runs/{_UNKNOWN}/sessions", headers=auth_header_user)
        assert response.status_code == 403

    def test_unknown_run_returns_empty_list(self, client: TestClient, auth_header_admin: dict) -> None:
        """Admin requesting sessions for a non-existent run receives an empty list (not 404)."""
        response = client.get(f"/eval/runs/{_UNKNOWN}/sessions", headers=auth_header_admin)
        assert response.status_code == 200
        assert response.json() == []
