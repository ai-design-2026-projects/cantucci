import uuid
from dataclasses import dataclass

@dataclass
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
