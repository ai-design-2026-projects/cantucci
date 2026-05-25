"""
Pytest plugin: provides the session-scoped ``db_url`` fixture.

Loaded automatically via ``addopts = "-p tests.db.test_config"`` in pyproject.toml.
Boots a throwaway pgvector/pgvector:pg16 container, applies all migrations, sets
DATABASE_URL and AUTH_SECRET in the environment so the backend pool can connect,
and tears everything down after the session.
"""

import os
import pytest
from testcontainers.postgres import PostgresContainer

from db.apply import apply
from backend.data_access.connection import close_pool

_PGVECTOR_IMAGE = "pgvector/pgvector:pg16"


@pytest.fixture(scope="session")
def db_url() -> str:
    """Yield a Postgres connection URL backed by a fresh migrated container.

    Sets DATABASE_URL and AUTH_SECRET environment variables so the backend
    connection pool and EnvSettings pick up the test database.
    Tears down the pool and the container when the session ends.

    Returns:
        psycopg-compatible connection URL string.
    """
    with PostgresContainer(image=_PGVECTOR_IMAGE) as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        apply(database_url=url)
        os.environ["DATABASE_URL"] = url
        os.environ["AUTH_SECRET"] = "test-secret-not-for-production"
        yield url
        close_pool()
