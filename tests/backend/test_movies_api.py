"""Smoke tests for the movies endpoints.

``POST /movies/batch`` with unknown IDs is already covered by the existing
``test_smoke.py``; this file extends with the remaining routes.

Covers:
- GET /movies/umap-points — 200 with empty list (no catalogue).
- GET /movies/{movie_id} — 404 for an unknown ID.
"""
import pytest
from fastapi.testclient import TestClient


class TestGetUmapPoints:
    """GET /movies/umap-points"""

    def test_empty_catalogue_returns_200(self, client: TestClient) -> None:
        """An empty catalogue returns 200 with an empty list (no catalogue seeded in tests)."""
        response = client.get("/movies/umap-points")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestGetMovie:
    """GET /movies/{movie_id}"""

    def test_unknown_id_returns_404(self, client: TestClient) -> None:
        """Requesting a movie with a non-existent ID returns 404."""
        response = client.get("/movies/999999999")
        assert response.status_code == 404
