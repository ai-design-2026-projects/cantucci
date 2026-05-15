"""Backend smoke-test fixtures: FastAPI TestClient bound to the test DB."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client(db_url: str, mini_catalogue: int) -> TestClient:
    """Yield a TestClient whose lifespan has booted against the test database.

    Depending on ``mini_catalogue`` ensures the catalogue is fully ingested
    before the orchestrator (and any retrieval call inside it) ever runs. The
    context manager triggers the FastAPI lifespan, which preloads the embedding
    model — that cost is paid once per session.
    """
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client
