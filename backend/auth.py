import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel

import backend.repository.users as api_users
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


def set_auth_cookie(response: Response, token: str) -> None:
    """Attach the JWT as an HttpOnly cookie to ``response``.

    Args:
        response: FastAPI response object to attach the cookie to.
        token:    Signed JWT string (from ``encode_token``).
    """
    env = get_env()
    response.set_cookie(
        key="auth_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=env.jwt_ttl_seconds,
        path="/",
    )


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


def _token_from_request(request: Request, authorization: str | None) -> str | None:
    """Extract a raw JWT from the cookie (preferred) or the Authorization header.

    Args:
        request:       FastAPI request carrying cookies.
        authorization: Value of the ``Authorization`` header, if present.

    Returns:
        Raw JWT string, or ``None`` if neither source has a token.

    Raises:
        HTTPException(401): If an Authorization header is present but malformed.
    """
    if cookie := request.cookies.get("auth_token"):
        return cookie

    if authorization is None:
        return None

    if not authorization.startswith("Bearer "):
        client_ip = request.client.host if request.client else ""
        _auth_log.warning("token_invalid", extra={"token_tail": "", "client_ip": client_ip, "outcome": "malformed_header"})
        raise HTTPException(status_code=401, detail="Authorization header must be 'Bearer <token>'.")

    return authorization.removeprefix("Bearer ")


def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """FastAPI dependency — resolve the cookie or bearer token to a User, or return None.

    Prefers the ``auth_token`` HttpOnly cookie; falls back to the
    ``Authorization: Bearer <token>`` header for non-browser clients.
    Anonymous requests (no token anywhere) return ``None``.
    Requests with a malformed or expired token raise 401 immediately.

    Args:
        request:       FastAPI request (injected by the DI framework).
        authorization: Value of the ``Authorization`` header, if present.

    Returns:
        Authenticated ``User`` or ``None`` for anonymous callers.

    Raises:
        HTTPException(401): If a token is present but invalid or expired.
    """
    token = _token_from_request(request, authorization)
    if token is None:
        return None

    client_ip = request.client.host if request.client else ""
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
