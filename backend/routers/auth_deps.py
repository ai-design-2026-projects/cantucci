import logging
from typing import Annotated

from fastapi import Header, HTTPException, Request

from backend.auth.tokens import decode_token, token_from_request
from backend.auth.types import User
from backend.data_access.users.queries import get_user_by_id

log = logging.getLogger(__name__)
_auth_log = logging.getLogger("auth")


def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """FastAPI dependency — resolve the cookie or bearer token to a User, or return None.

    Requests with a malformed or expired token raise 401 immediately.

    Args:
        request:       FastAPI request (injected by the DI framework).
        authorization: Value of the ``Authorization`` header, if present.

    Returns:
        Authenticated ``User`` or ``None`` for anonymous callers.

    Raises:
        HTTPException(401): If a token is present but invalid or expired.
    """
    token = token_from_request(request, authorization)
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
