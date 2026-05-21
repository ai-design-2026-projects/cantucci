from pydantic import BaseModel, EmailStr, field_validator

from backend.auth.types import User


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
        """Reject passwords shorter than 8 characters.

        Args:
            v: The raw password value from the request body.

        Returns:
            The validated password.

        Raises:
            ValueError: If the password is shorter than 8 characters.
        """
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
