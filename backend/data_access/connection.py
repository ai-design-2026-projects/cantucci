import logging
from contextlib import contextmanager
from typing import Generator
import psycopg
import psycopg_pool
from psycopg.rows import dict_row

from backend.settings import get_env

log = logging.getLogger(__name__)

# Module-level pool, lazily created on first use. Implements a singleton pattern for the connection pool
_pool: psycopg_pool.ConnectionPool | None = None
# Adjust based on expected concurrency and DB limits
MAX_POOL_SIZE = 10

def _get_pool() -> psycopg_pool.ConnectionPool:
    """Return the module-level connection pool, creating it on first use."""
    global _pool
    if _pool is None:
        conninfo = get_env().database_url
        if not conninfo:
            raise RuntimeError(
                "DATABASE_URL is not set. The backend API and DB-writing "
                "ingestion paths require a Postgres connection string."
            )
        _pool = psycopg_pool.ConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=MAX_POOL_SIZE,
            open=True,
            configure=_configure_connection,
        )
    return _pool


def _configure_connection(conn: psycopg.Connection) -> None:
    """Register pgvector type adapter and set dict_row as default on every new connection."""
    from pgvector.psycopg import register_vector
    register_vector(conn)
    conn.row_factory = dict_row


@contextmanager
def transaction() -> Generator[psycopg.Connection, None, None]:
    """
    Yield a connection inside an explicit transaction.
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
