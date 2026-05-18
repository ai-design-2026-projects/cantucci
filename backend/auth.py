"""JWT authentication utilities and FastAPI dependencies.

Public surface:
    hash_password / verify_password  — bcrypt helpers
    encode_token / decode_token      — JWT sign / verify (PyJWT)
    get_current_user                 — FastAPI dependency; returns User | None
    require_admin                    — FastAPI dependency; raises 403 if not admin

The JWT signing secret comes from ``EnvSettings.auth_secret`` (env var
``AUTH_SECRET``). Token TTL comes from ``EnvSettings.jwt_ttl_seconds``.
Nothing auth-related is hard-coded here.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel

from backend.api import users as api_users
from backend.settings import get_env

log = logging.getLogger(__name__)
_auth_log = logging.getLogger("auth")


class User(BaseModel):
    """Authenticated user attached to a request by ``get_current_user``.

    Attributes:
        id:    UUID primary key.
        email: Unique email address.
        role:  Role name (e.g. ``"admin"`` or ``"user"``).
    """

    id: uuid.UUID
    email: str
    role: str


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of ``plain``.

    Args:
        plain: Plaintext password.

    Returns:
        bcrypt hash string safe to store in the DB.
    """
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if ``plain`` matches ``hashed``.

    Args:
        plain:  Plaintext candidate password.
        hashed: bcrypt hash from the DB.

    Returns:
        True on match, False otherwise.
    """
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def encode_token(user_id: uuid.UUID) -> str:
    """Sign and return a JWT for ``user_id``.

    TTL is taken from ``EnvSettings.jwt_ttl_seconds`` (env, default 7 days).
    Signing key is taken from ``EnvSettings.auth_secret`` (env).

    Args:
        user_id: UUID of the authenticated user.

    Returns:
        Signed JWT string.
    """
    env = get_env()
    secret = env.auth_secret
    exp = int(datetime.now(timezone.utc).timestamp()) + env.jwt_ttl_seconds
    return jwt.encode({"sub": str(user_id), "exp": exp}, secret, algorithm="HS256")


def decode_token(token: str, *, client_ip: str = "") -> uuid.UUID:
    """Verify a JWT and return the ``user_id`` from its ``sub`` claim.

    Args:
        token:     JWT string (without the ``Bearer `` prefix).
        client_ip: Requester IP for auth log records.

    Returns:
        UUID extracted from the ``sub`` claim.

    Raises:
        HTTPException(401): On invalid signature, malformed token, or expiry.
    """
    secret = get_env().auth_secret
    tail = token[-8:] if len(token) >= 8 else token
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return uuid.UUID(payload["sub"])
    except jwt.ExpiredSignatureError:
        _auth_log.info("token_expired", extra={"token_tail": tail, "client_ip": client_ip})
        raise HTTPException(status_code=401, detail="Token expired.")
    except (jwt.InvalidTokenError, KeyError, ValueError):
        _auth_log.warning("token_invalid", extra={"token_tail": tail, "client_ip": client_ip})
        raise HTTPException(status_code=401, detail="Invalid token.")


def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """FastAPI dependency — resolve the bearer token to a User, or return None.

    Anonymous requests (no ``Authorization`` header) return ``None``.
    Requests with a malformed or expired token raise 401 immediately.

    Args:
        request:       FastAPI request (injected by the DI framework).
        authorization: Value of the ``Authorization`` header, if present. This should be in the format ``Bearer <token>``.

    Returns:
        Authenticated ``User`` or ``None`` for anonymous callers.

    Raises:
        HTTPException(401): If the header is present but the token is invalid.
    """
    # If there's no Authorization header, we just return None (anonymous). 
    # It means that no token was provided, so we don't even attempt to decode anything or log an auth event
    if authorization is None:
        return None

    client_ip = request.client.host if request.client else ""

    if not authorization.startswith("Bearer "):
        _auth_log.warning("token_invalid", extra={"token_tail": "", "client_ip": client_ip, "outcome": "malformed_header"})
        raise HTTPException(status_code=401, detail="Authorization header must be 'Bearer <token>'.")

    token = authorization.removeprefix("Bearer ")
    user_id = decode_token(token, client_ip=client_ip)

    row = api_users.get_user_by_id(user_id)
    if row is None:
        _auth_log.warning("token_invalid", extra={"token_tail": token[-8:], "client_ip": client_ip, "outcome": "user_not_found"})
        raise HTTPException(status_code=401, detail="User not found.")

    _auth_log.debug("token_decoded", extra={"user_id": str(row.id), "client_ip": client_ip})
    return User(id=row.id, email=row.email, role=row.role)


def require_admin(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user)],
) -> User:
    """FastAPI dependency — require an authenticated admin user.

    Args:
        request: FastAPI request (for path logging).
        user:    Result of ``get_current_user``.

    Returns:
        The authenticated admin ``User``.

    Raises:
        HTTPException(401): If the request is anonymous.
        HTTPException(403): If the user is not an admin.
    """
    path = request.url.path
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    if user.role != "admin":
        _auth_log.warning("admin_access_denied", extra={"user_id": str(user.id), "role": user.role, "path": path})
        raise HTTPException(status_code=403, detail="Admin access required.")

    _auth_log.info("admin_access_granted", extra={"user_id": str(user.id), "path": path})
    return user
