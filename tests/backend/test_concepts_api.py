"""Smoke tests for the concepts endpoints.

Covers:
- GET /concepts/{concept_id}/axis — 404 for an unknown UUID.
"""
import uuid

import pytest
from fastapi.testclient import TestClient


class TestGetConceptAxis:
    """GET /concepts/{concept_id}/axis"""

    def test_unknown_id_returns_404(self, client: TestClient) -> None:
        """Requesting the axis for a non-existent concept returns 404."""
        response = client.get(f"/concepts/{uuid.uuid4()}/axis")
        assert response.status_code == 404
