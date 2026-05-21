import logging
import uuid
from datetime import datetime, timezone
import jwt
from fastapi import HTTPException, Response

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


def decode_token(token: str, *, client_ip: str = "") -> uuid.UUID:
    """
    Verify a JWT and return the ``user_id`` from its ``sub`` claim.
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
