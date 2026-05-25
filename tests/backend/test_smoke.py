"""Backend smoke test: app boots and serves against the migrated test DB."""

from fastapi.testclient import TestClient

from backend.app import app


def test_movies_batch_empty(db_url: str) -> None:
    """POST /movies/batch with unknown IDs returns 200 and an empty list.

    Exercises the full app → data_access → Postgres path on an empty catalogue.

    Args:
        db_url: Connection URL from the ``db_url`` session fixture (wires the pool).
    """
    with TestClient(app) as client:
        response = client.post("/movies/batch", json={"ids": [999999999]})
    assert response.status_code == 200
    assert response.json() == []


def test_openapi_docs_available(db_url: str) -> None:
    """GET /docs returns 200, confirming the app boots and OpenAPI schema generates.

    Args:
        db_url: Connection URL from the ``db_url`` session fixture.
    """
    with TestClient(app) as client:
        response = client.get("/docs")
    assert response.status_code == 200
