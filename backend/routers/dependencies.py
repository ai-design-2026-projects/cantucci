import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from backend.auth.tokens import decode_token
from backend.auth.types import User
from backend.data_access.users.queries import get_user_by_id

log = logging.getLogger(__name__)
_auth_log = logging.getLogger("auth")


def _token_from_request(
    request: Request,
    authorization: str | None
) -> str | None:
    """
    Extract a raw JWT from the cookie (preferred) or the Authorization header.
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
    """
    FastAPI dependency — resolve the cookie or bearer token to a User, or return None.
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

    row = get_user_by_id(user_id)
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
