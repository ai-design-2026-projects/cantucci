"""Smoke tests for the cluster-snapshots endpoints.

Covers:
- GET /cluster-snapshots/{id}                        — 404 for an unknown UUID.
- GET /cluster-snapshots/{id}/clusters/{id}/members  — 404 for an unknown snapshot.
- DELETE /cluster-snapshots/{id}                     — 404 for an unknown UUID (no auth
                                                        dependency is present on this endpoint;
                                                        api.md states "401 if anonymous" but the
                                                        current code does not enforce it).
"""
import uuid

import pytest
from fastapi.testclient import TestClient


_UNKNOWN_SNAPSHOT = uuid.uuid4()
_UNKNOWN_CLUSTER = uuid.uuid4()


class TestGetClusterSnapshot:
    """GET /cluster-snapshots/{cluster_snapshot_id}"""

    def test_unknown_id_returns_404(self, client: TestClient) -> None:
        """Requesting a non-existent snapshot returns 404."""
        response = client.get(f"/cluster-snapshots/{_UNKNOWN_SNAPSHOT}")
        assert response.status_code == 404


class TestGetClusterMembers:
    """GET /cluster-snapshots/{snapshot_id}/clusters/{cluster_id}/members"""

    def test_unknown_snapshot_returns_404(self, client: TestClient) -> None:
        """Requesting members of a non-existent snapshot returns 404."""
        response = client.get(
            f"/cluster-snapshots/{_UNKNOWN_SNAPSHOT}/clusters/{_UNKNOWN_CLUSTER}/members"
        )
        assert response.status_code == 404


class TestDeleteClusterSnapshot:
    """DELETE /cluster-snapshots/{cluster_snapshot_id}"""

    def test_unknown_id_returns_404(self, client: TestClient) -> None:
        """Deleting a non-existent snapshot returns 404 (ClusterSnapshotNotFound).

        Note: the api.md contract states this endpoint should require authentication,
        but the current router has no auth dependency — the 401 path is not enforced.
        """
        response = client.delete(f"/cluster-snapshots/{_UNKNOWN_SNAPSHOT}")
        assert response.status_code == 404
