"""Pytest plugin: boot a pgvector Postgres, apply migrations, ingest mini set.

Registered globally via pyproject.toml ``addopts = "-p tests.db.test_config"`` so
both ``tests/db`` and ``tests/backend`` share the same session-scoped database.

Smoke tests are read-only against the catalogue — re-applying migrations or
re-ingesting per test would dominate runtime, so the schema is reset once at
session start. Per-test isolation comes from each test using unique session/run
IDs rather than schema teardown.

The fixture relies on the HF artifacts pinned in ``configs/test.yaml`` (under the
``ingestion`` block) to pull the mini parquet — the same path production uses,
no test-specific shortcut.
"""

from __future__ import annotations

import os
from pathlib import Path

# Pin the smoke-test config before any backend import reads CONFIG_PATH.
# Module-level execution happens at plugin registration (pytest startup), which
# is earlier than any fixture or test collection that might call get_settings().
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("CONFIG_PATH", str(_PROJECT_ROOT / "configs" / "test.yaml"))

# Docker Desktop on macOS exposes its daemon socket at ~/.docker/run/docker.sock
# rather than the canonical /var/run/docker.sock that docker-py / testcontainers
# probe by default. Point DOCKER_HOST at the user socket when the canonical one
# is absent — no-op on Linux/CI where /var/run/docker.sock exists, and no-op
# when the developer has already exported DOCKER_HOST themselves.
if "DOCKER_HOST" not in os.environ:
    _user_sock = Path.home() / ".docker" / "run" / "docker.sock"
    if not Path("/var/run/docker.sock").exists() and _user_sock.exists():
        os.environ["DOCKER_HOST"] = f"unix://{_user_sock}"

import pytest
from testcontainers.postgres import PostgresContainer

from backend.api.db import close_pool
from db.apply import apply
from db.ingest import run_from_artifact


_PGVECTOR_IMAGE = "pgvector/pgvector:pg16"


@pytest.fixture(scope="session")
def _postgres_container() -> PostgresContainer:
    """Boot a pgvector-enabled Postgres container for the whole test session."""
    container = PostgresContainer(_PGVECTOR_IMAGE, driver=None)
    container.start()
    try:
        yield container
    finally:
        close_pool()
        container.stop()


@pytest.fixture(scope="session")
def db_url(_postgres_container: PostgresContainer) -> str:
    """Return the connection string of the test Postgres and pin DATABASE_URL.

    Exporting DATABASE_URL into the process environment lets every downstream
    module that reads ``get_env().database_url`` (api/db, apply, ingest, …)
    pick it up without a second injection mechanism.
    """
    url = _postgres_container.get_connection_url()
    # testcontainers returns ``postgresql+psycopg2://...`` by default; psycopg v3
    # accepts the bare ``postgresql://`` form.
    if "+" in url.split("://", 1)[0]:
        scheme, rest = url.split("://", 1)
        url = f"{scheme.split('+', 1)[0]}://{rest}"
    os.environ["DATABASE_URL"] = url
    return url


@pytest.fixture(scope="session")
def mini_catalogue(db_url: str) -> int:
    """Apply migrations and ingest the mini artifact from HF; return movie count.

    Runs once per test session. Subsequent tests query the populated catalogue
    without re-running the pipeline.
    """
    apply(database_url=db_url)
    run_from_artifact("mini")

    import psycopg
    with psycopg.connect(db_url) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM movies").fetchone()
    assert rows is not None, "movies table missing after ingest"
    count = rows[0]
    # The mini parquet's actual row count is a property of the snapshot pinned
    # in ingestion.artifacts.mini, not of split.mini_size (which only drives
    # stage-2 split creation, not test reads). Asserting equality against the
    # config would break every time the snapshot is regenerated with a
    # different mini_size; assert non-emptiness instead.
    assert count > 0, "mini catalogue ingested zero rows"
    return count
