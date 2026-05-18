"""CRUD operations for the users and roles tables.

Follows the same pattern as the other api/ modules: all SQL runs inside
``transaction()`` from ``backend.api.db``; no other layer touches these tables.
"""

import logging
import uuid
from dataclasses import dataclass

from backend.api.db import transaction

log = logging.getLogger(__name__)


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


def create_user(email: str, password_hash: str, role_name: str) -> uuid.UUID:
    """Insert a new user row and return its UUID.

    Args:
        email:         Unique email address.
        password_hash: Pre-hashed password (use ``backend.auth.hash_password``).
        role_name:     Role name that must exist in the ``roles`` table.

    Returns:
        UUID of the newly created user.

    Raises:
        ValueError: If ``role_name`` does not exist in the roles table.
        psycopg.errors.UniqueViolation: If ``email`` is already registered.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO users (email, password_hash, role_id)
            SELECT %s, %s, id FROM roles WHERE name = %s
            RETURNING id
            """,
            (email, password_hash, role_name),
        ).fetchone()

    if row is None:
        raise ValueError(f"Role '{role_name}' not found in the roles table.")

    user_id: uuid.UUID = row[0]
    log.debug("created user %s role=%s", user_id, role_name)
    return user_id


def get_user_by_email(email: str) -> UserRow | None:
    """Fetch a user row joined with its role name, looked up by email.

    Args:
        email: Email address to look up.

    Returns:
        A ``UserRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.email, u.password_hash, r.name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.email = %s
            """,
            (email,),
        ).fetchone()

    if row is None:
        return None
    return UserRow(id=row[0], email=row[1], password_hash=row[2], role=row[3])


def get_user_by_id(user_id: uuid.UUID) -> UserRow | None:
    """Fetch a user row joined with its role name, looked up by UUID.

    Args:
        user_id: UUID primary key.

    Returns:
        A ``UserRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.email, u.password_hash, r.name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.id = %s
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        return None
    return UserRow(id=row[0], email=row[1], password_hash=row[2], role=row[3])
