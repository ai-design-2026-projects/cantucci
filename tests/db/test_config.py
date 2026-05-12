"""
Pytest fixtures for database-backed tests.

Each test that requests `db_url` or `db_conn` gets an isolated Postgres schema
so tests never share state. The testcontainers library boots a throwaway
pgvector container for the test session.

Note: `check_same_thread` is a SQLite-only parameter and is not relevant for
Postgres. Tests use a real Postgres instance so pgvector behaviour is
identical to production.
"""

import os

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

import backend.api.db as db_module
from db.apply import apply


PGVECTOR_IMAGE = "pgvector/pgvector:pg16"


@pytest.fixture(scope="session")
def postgres_container():
    """Start a pgvector Postgres container for the test session."""
    with PostgresContainer(image=PGVECTOR_IMAGE) as container:
        yield container


@pytest.fixture()
def db_url(postgres_container, monkeypatch):
    """Return a DATABASE_URL pointing at a fresh schema for this test.

    Creates a unique schema, applies all migrations inside it, yields the URL,
    then drops the schema on teardown.
    """
    base_url = postgres_container.get_connection_url().replace("+psycopg2", "")

    schema = f"test_{os.urandom(6).hex()}"

    with psycopg.connect(base_url, autocommit=True) as setup_conn:
        setup_conn.execute(f'CREATE SCHEMA "{schema}"')
        setup_conn.execute(f'SET search_path TO "{schema}"')

    schema_url = f"{base_url}?options=-csearch_path%3D{schema}"

    monkeypatch.setenv("DATABASE_URL", schema_url)

    # Close any pooled connections so the pool picks up the new DATABASE_URL.
    db_module.close_pool()

    apply(database_url=schema_url)

    yield schema_url

    db_module.close_pool()

    with psycopg.connect(base_url, autocommit=True) as teardown_conn:
        teardown_conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture()
def db_conn(db_url):
    """Yield a plain psycopg connection for raw SQL assertions in tests."""
    with psycopg.connect(db_url) as conn:
        yield conn
