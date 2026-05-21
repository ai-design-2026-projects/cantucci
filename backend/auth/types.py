import uuid
from pydantic import BaseModel


class User(BaseModel):
    """
    Authenticated user attached to a request by ``get_current_user``.
    Attributes:
        id:    UUID primary key.
        email: Unique email address.
        role:  Role name (e.g. ``"admin"`` or ``"user"``).
    """
    id: uuid.UUID
    email: str
    role: str
