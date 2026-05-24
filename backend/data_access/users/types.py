import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserRow:
    """Projection of a users row joined with its role name.

    Attributes:
        id:            UUID primary key.
        email:         Unique email address.
        password_hash: bcrypt hash; never returned to clients.
        role:          Role name resolved from the roles table (e.g. ``"admin"``).
    """
    id: uuid.UUID
    email: str
    password_hash: str
    role: str

    @classmethod
    def from_row(cls, r: dict) -> "UserRow":
        """Construct from a psycopg dict_row result (users JOIN roles)."""
        return cls(
            id=r["id"],
            email=r["email"],
            password_hash=r["password_hash"],
            role=r["name"],
        )
