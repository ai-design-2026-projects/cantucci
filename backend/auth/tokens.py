import logging
import uuid
from datetime import datetime, timezone
import jwt
from fastapi import HTTPException, Request, Response

from backend.exceptions import InvalidToken, TokenExpired
from backend.settings import get_env

log = logging.getLogger(__name__)
_auth_log = logging.getLogger("auth")


def encode_token(user_id: uuid.UUID) -> str:
    """
    Sign and return a JWT for ``user_id``.
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
    """
    Attach the JWT as an HttpOnly cookie to ``response``.
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


def token_from_request(request: Request, authorization: str | None) -> str | None:
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


def decode_token(token: str, *, client_ip: str = "") -> uuid.UUID:
    """
    Verify a JWT and return the ``user_id`` from its ``sub`` claim.
    Args:
        token:     JWT string (without the ``Bearer `` prefix).
        client_ip: Requester IP for auth log records.
    Returns:
        UUID extracted from the ``sub`` claim.
    Raises:
        TokenExpired: On an expired token.
        InvalidToken: On invalid signature, malformed token, or missing claims.
    """
    secret = get_env().auth_secret
    tail = token[-8:] if len(token) >= 8 else token
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return uuid.UUID(payload["sub"])
    except jwt.ExpiredSignatureError:
        _auth_log.info("token_expired", extra={"token_tail": tail, "client_ip": client_ip})
        raise TokenExpired()
    except (jwt.InvalidTokenError, KeyError, ValueError):
        _auth_log.warning("token_invalid", extra={"token_tail": tail, "client_ip": client_ip})
        raise InvalidToken()
