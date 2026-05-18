"""Authentication HTTP endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator

from backend.api import users as api_users
from backend.auth import User, encode_token, get_current_user, hash_password, verify_password

log = logging.getLogger(__name__)
_auth_log = logging.getLogger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Body for ``POST /auth/login`` and ``POST /auth/register``.

    Attributes:
        email:    User email address. Must be a valid email format.
        password: Plaintext password. Must be at least 8 characters.
    """

    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class LoginResponse(BaseModel):
    """Successful login response.

    Attributes:
        token: Signed JWT; include as ``Authorization: Bearer <token>``.
        user:  Basic user info (id, email, role).
    """

    token: str
    user: User


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    """Verify credentials and return a signed JWT.

    Args:
        body:    ``LoginRequest`` with email and password.
        request: FastAPI request (used for client IP in auth logs).

    Returns:
        ``LoginResponse`` with the token and user info on success.

    Raises:
        HTTPException(401): On unknown email or wrong password.
    """
    client_ip = request.client.host if request.client else ""

    row = api_users.get_user_by_email(body.email)
    if row is None or not verify_password(body.password, row.password_hash):
        _auth_log.info("login_failed", extra={"email": body.email, "client_ip": client_ip, "reason": "unknown_email_or_wrong_password"})
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    token = encode_token(row.id)
    user = User(id=row.id, email=row.email, role=row.role)
    _auth_log.info("login_success", extra={"user_id": str(row.id), "email": row.email, "client_ip": client_ip})
    return LoginResponse(token=token, user=user)


@router.post("/register", response_model=LoginResponse, status_code=201)
def register(body: LoginRequest, request: Request) -> LoginResponse:
    """Register a new user account with the ``user`` role and return a signed JWT.

    Admin accounts must be provisioned via ``python -m db.create_user --role admin``.

    Args:
        body:    ``LoginRequest`` with email and password.
        request: FastAPI request (used for client IP in auth logs).

    Returns:
        ``LoginResponse`` with the token and user info.

    Raises:
        HTTPException(409): If the email is already registered.
    """
    client_ip = request.client.host if request.client else "" 

    if api_users.get_user_by_email(body.email) is not None:
        _auth_log.info("register_failed", extra={"email": body.email, "client_ip": client_ip, "reason": "email_taken"})
        raise HTTPException(status_code=409, detail="Email already registered.")
    password_hash = hash_password(body.password)
    user_id = api_users.create_user(body.email, password_hash, "user")
    token = encode_token(user_id)
    _auth_log.info("register_success", extra={"user_id": str(user_id), "email": body.email, "client_ip": client_ip})
    return LoginResponse(token=token, user=User(id=user_id, email=body.email, role="user"))


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
