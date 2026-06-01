"""Smoke tests for the authentication dependency layer.

Exercises ``require_admin`` / ``get_current_user`` / ``decode_token`` via the
``GET /eval/personas`` admin-gated route, which is a minimal and stable target.

Covers:
- No token → 401.
- Malformed Authorization header → 401.
- Expired JWT → 401.
- Valid token for a non-admin user → 403.
- Valid token for an admin user → 200.
"""
import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.settings import get_env


@pytest.fixture()
def _route() -> str:
    """Return the URL used to exercise the admin auth gate.

    Returns:
        Stable, side-effect-free URL protected by ``require_admin``.
    """
    return "/eval/personas"


def _expired_token(user_id: uuid.UUID) -> str:
    """Mint a JWT whose expiry is one second in the past.

    Args:
        user_id: UUID to embed in the ``sub`` claim.

    Returns:
        Signed but expired JWT string.
    """
    env = get_env()
    exp = int(time.time()) - 1
    return jwt.encode({"sub": str(user_id), "exp": exp}, env.auth_secret, algorithm="HS256")


class TestNoAuth:
    """Requests without any credential are rejected."""

    def test_no_auth_header_returns_401(self, client: TestClient, _route: str) -> None:
        """A request with no Authorization header or cookie receives 401."""
        response = client.get(_route)
        assert response.status_code == 401


class TestMalformedToken:
    """Invalid Authorization headers are rejected before any DB lookup."""

    def test_malformed_bearer_header_returns_401(self, client: TestClient, _route: str) -> None:
        """A header that is not 'Bearer <token>' is rejected with 401."""
        response = client.get(_route, headers={"Authorization": "Token abc"})
        assert response.status_code == 401

    def test_corrupted_token_returns_401(self, client: TestClient, _route: str) -> None:
        """A syntactically valid Bearer prefix but garbage token body returns 401."""
        response = client.get(_route, headers={"Authorization": "Bearer notajwt.notajwt.notajwt"})
        assert response.status_code == 401


class TestExpiredToken:
    """Expired JWTs are rejected with 401."""

    def test_expired_token_returns_401(self, client: TestClient, _route: str, admin_token: str) -> None:
        """An expired JWT (past ``exp``) is rejected even if the signature is valid."""
        user_id = uuid.uuid4()
        token = _expired_token(user_id)
        response = client.get(_route, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


class TestNonAdminToken:
    """Valid tokens for non-admin users are rejected with 403."""

    def test_user_token_returns_403(self, client: TestClient, _route: str, user_token: str) -> None:
        """A valid token for a role='user' account is rejected with 403 on an admin route."""
        response = client.get(_route, headers={"Authorization": f"Bearer {user_token}"})
        assert response.status_code == 403


class TestAdminToken:
    """Valid admin tokens are accepted."""

    def test_admin_token_returns_200(self, client: TestClient, _route: str, admin_token: str) -> None:
        """A valid token for a role='admin' account receives 200 on the admin route."""
        response = client.get(_route, headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
