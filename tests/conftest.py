"""Shared pytest fixtures for the entire test suite.

Provides:
- ``_clean_db``     — autouse, function-scoped: TRUNCATEs mutable tables before every test.
- ``admin_token``   — seeds an admin user and returns a signed JWT.
- ``user_token``    — seeds a regular user and returns a signed JWT.
- ``client``        — FastAPI TestClient with the full lifespan wired.
- ``seed_run``      — seeds a minimal eval run and returns its UUID.
- ``seed_persona``  — seeds an eval persona and returns its UUID.
- ``seed_ground_truth`` — seeds a ground-truth row and returns its UUID.
- ``seed_session``  — seeds an eval session (needs a run_id and conversation_id).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.auth.passwords import hash_password
from backend.auth.tokens import encode_token
from backend.data_access.connection import transaction
from backend.data_access.conversations.queries import create_conversation
from backend.data_access.eval.queries import (
    create_eval_session,
    create_ground_truth,
    create_persona,
    create_run,
)
from backend.data_access.users.queries import create_user


@pytest.fixture(autouse=True)
def _clean_db(db_url: str) -> None:
    """Truncate all mutable tables before each test.

    The ``RESTART IDENTITY CASCADE`` clause clears all tables that reference
    the listed ones (eval_sessions, turn_intents, conversation_metrics,
    judge_scores, messages, conversation_snapshot_refs, …) without touching
    the movie catalogue or schema_migrations.

    Args:
        db_url: Connection URL from the session-scoped ``db_url`` fixture (wires the pool).
    """
    with transaction() as conn:
        conn.execute(
            "TRUNCATE users, runs, personas, ground_truths, conversations RESTART IDENTITY CASCADE"
        )


@pytest.fixture()
def admin_token() -> str:
    """Seed an admin user and return a signed JWT for that user.

    Returns:
        Signed JWT string accepted by ``Authorization: Bearer <token>``.
    """
    user_id = create_user(
        email=f"admin-{uuid.uuid4()}@test.local",
        password_hash=hash_password("secret"),
        role_name="admin",
    )
    return encode_token(user_id)


@pytest.fixture()
def user_token() -> str:
    """Seed a regular (non-admin) user and return a signed JWT.

    Returns:
        Signed JWT string accepted by ``Authorization: Bearer <token>``.
    """
    user_id = create_user(
        email=f"user-{uuid.uuid4()}@test.local",
        password_hash=hash_password("secret"),
        role_name="user",
    )
    return encode_token(user_id)


@pytest.fixture()
def client() -> TestClient:
    """Return a FastAPI TestClient with the full app lifespan active.

    Returns:
        Configured ``TestClient`` instance.
    """
    with TestClient(app) as c:
        return c


def seed_run(
    name: str = "test-run",
    condition: str = "conversational",
    seed: int = 42,
) -> uuid.UUID:
    """Insert a minimal eval run and return its UUID.

    Args:
        name:      Human-readable label.
        condition: Experimental condition.
        seed:      RNG seed.

    Returns:
        UUID of the newly created run.
    """
    return create_run(
        config_hash="abc12345",
        config_snapshot={"test": True},
        seed=seed,
        name=name,
        condition=condition,
    )


def seed_persona(slug: str = "test-persona") -> uuid.UUID:
    """Insert a minimal eval persona and return its UUID.

    Args:
        slug: Unique persona identifier.

    Returns:
        UUID of the newly created persona.
    """
    return create_persona(slug=slug)


def seed_ground_truth(slug: str = "test-gt") -> uuid.UUID:
    """Insert a minimal ground-truth row and return its UUID.

    Args:
        slug: Unique ground-truth identifier.

    Returns:
        UUID of the newly created ground-truth.
    """
    return create_ground_truth(
        slug=slug,
        intent_description="Test intent description.",
        operations=[{"op": "partition_by", "concept": "genre"}],
        prompt_hash="a" * 64,
    )


def seed_conversation() -> uuid.UUID:
    """Insert a minimal anonymous conversation and return its UUID.

    Returns:
        UUID of the newly created conversation.
    """
    return create_conversation(user_id=None, config_snapshot={"test": True})


def seed_eval_session(
    run_id: uuid.UUID,
    conversation_id: uuid.UUID,
    persona_id: uuid.UUID | None = None,
    ground_truth_id: uuid.UUID | None = None,
    seed: int = 1,
) -> uuid.UUID:
    """Insert a minimal eval session and return its UUID.

    Args:
        run_id:          Parent run UUID.
        conversation_id: Linked conversation UUID.
        persona_id:      Optional persona UUID.
        ground_truth_id: Optional ground-truth UUID.
        seed:            Per-session RNG seed.

    Returns:
        UUID of the newly created eval session.
    """
    return create_eval_session(
        run_id=run_id,
        conversation_id=conversation_id,
        seed=seed,
        persona_id=persona_id,
        ground_truth_id=ground_truth_id,
    )
