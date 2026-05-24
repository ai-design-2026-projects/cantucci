import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.data_access.users.queries import create_user, get_user_by_email
from backend.routers.auth_deps import get_current_user
from backend.auth.passwords import hash_password, verify_password
from backend.auth.tokens import encode_token, set_auth_cookie
from backend.auth.types import User
from backend.routers.dto.users.dtos import LoginRequest, LoginResponse

log = logging.getLogger(__name__)
_auth_log = logging.getLogger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    """Verify credentials, set an HttpOnly cookie, and return a signed JWT.

    Args:
        body:     ``LoginRequest`` with email and password.
        request:  FastAPI request (used for client IP in auth logs).
        response: FastAPI response (used to set the ``auth_token`` cookie).

    Returns:
        ``LoginResponse`` with the token and user info on success.

    Raises:
        HTTPException(401): On unknown email or wrong password.
    """
    client_ip = request.client.host if request.client else ""

    row = get_user_by_email(body.email)
    if row is None or not verify_password(body.password, row.password_hash):
        _auth_log.info("login_failed", extra={"email": body.email, "client_ip": client_ip, "reason": "unknown_email_or_wrong_password"})
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    token = encode_token(row.id)
    user = User(id=row.id, email=row.email, role=row.role)
    set_auth_cookie(response, token)
    _auth_log.info("login_success", extra={"user_id": str(row.id), "email": row.email, "client_ip": client_ip})
    return LoginResponse(token=token, user=user)


@router.post("/register", response_model=LoginResponse, status_code=201)
def register(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    """Register a new user account with the ``user`` role, set an HttpOnly cookie, and return a signed JWT.

    Admin accounts must be provisioned via ``python -m db.create_user --role admin``.

    Args:
        body:     ``LoginRequest`` with email and password.
        request:  FastAPI request (used for client IP in auth logs).
        response: FastAPI response (used to set the ``auth_token`` cookie).

    Returns:
        ``LoginResponse`` with the token and user info.

    Raises:
        HTTPException(409): If the email is already registered.
    """
    client_ip = request.client.host if request.client else ""

    if get_user_by_email(body.email) is not None:
        _auth_log.info("register_failed", extra={"email": body.email, "client_ip": client_ip, "reason": "email_taken"})
        raise HTTPException(status_code=409, detail="Email already registered.")
    password_hash = hash_password(body.password)
    user_id = create_user(body.email, password_hash, "user")
    token = encode_token(user_id)
    set_auth_cookie(response, token)
    _auth_log.info("register_success", extra={"user_id": str(user_id), "email": body.email, "client_ip": client_ip})
    return LoginResponse(token=token, user=User(id=user_id, email=body.email, role="user"))


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    """Clear the ``auth_token`` HttpOnly cookie to log the user out.

    This endpoint performs no server-side token revocation — it only instructs
    the browser to discard the cookie. The JWT remains technically valid until
    its ``exp`` claim passes.

    Args:
        response: FastAPI response (used to clear the ``auth_token`` cookie).

    Returns:
        ``204 No Content`` on success.
    """
    response.delete_cookie(key="auth_token", path="/")
    log.debug("logout_cookie_cleared")


@router.get("/me", response_model=User)
def me(user: User | None = Depends(get_current_user)) -> User:
    """Return the currently authenticated user.

    Args:
        user: Resolved by the ``get_current_user`` dependency.

    Returns:
        The authenticated ``User``.

    Raises:
        HTTPException(401): If the request is anonymous or the token is invalid.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user
