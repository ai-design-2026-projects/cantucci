"""
Database connection pool and transaction helper.

This module is the only place in the codebase that opens Postgres connections.
All other api/ modules import `transaction` from here — they never call psycopg directly.

Usage:
    from backend.api.db import transaction

    with transaction() as conn:
        conn.execute("SELECT 1")
"""

import logging
from contextlib import contextmanager
from typing import Generator

import psycopg
import psycopg_pool

from backend.settings import database_url

log = logging.getLogger(__name__)

# Module-level pool, lazily created on first use.
_pool: psycopg_pool.ConnectionPool | None = None


def _get_pool() -> psycopg_pool.ConnectionPool:
    """Return the module-level connection pool, creating it on first use."""
    global _pool
    if _pool is None:
        _pool = psycopg_pool.ConnectionPool(
            conninfo=database_url(),
            min_size=1,
            max_size=10,
            open=True,
            configure=_configure_connection,
        )
    return _pool


def _configure_connection(conn: psycopg.Connection) -> None:
    """Register pgvector type adapter on every new connection."""
    from pgvector.psycopg import register_vector
    register_vector(conn)


@contextmanager
def transaction() -> Generator[psycopg.Connection, None, None]:
    """Yield a connection inside an explicit transaction.

    Commits on clean exit, rolls back on any exception. Callers should never
    call conn.commit() or conn.rollback() themselves.
    """
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.transaction():
            yield conn


def close_pool() -> None:
    """Close the connection pool. Call this at process shutdown or in test teardown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
