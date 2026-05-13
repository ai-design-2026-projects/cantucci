"""
Unit tests for backend/cluster/tools/soft_cluster_engine.py.

No database or LLM calls — uses synthetic NumPy arrays only.
"""

import numpy as np
import pytest

from backend.cluster.tools.soft_cluster_engine import SoftClusterResult, cluster


class TestCluster:
    def test_two_blob_synthetic(self):
        rng = np.random.default_rng(42)
        blob_a = rng.normal(loc=0.0, scale=0.1, size=(20, 4)).astype(np.float32)
        blob_b = rng.normal(loc=5.0, scale=0.1, size=(20, 4)).astype(np.float32)
        embeddings = np.vstack([blob_a, blob_b])

        result = cluster(embeddings, min_cluster_size=5, min_samples=2)

        assert isinstance(result, SoftClusterResult)
        assert result.n_clusters == 2
        assert result.membership is not None
        assert result.membership.shape == (40, 2)
        assert (result.membership >= 0).all(), "membership values must be non-negative"
        assert (result.membership <= 1 + 1e-5).all(), "membership values must be <= 1"
        row_sums = result.membership.sum(axis=1)
        assert (row_sums <= 1.0 + 1e-5).all(), "row sums must not exceed 1"

    def test_all_noise_returns_n_clusters_zero(self):
        rng = np.random.default_rng(0)
        embeddings = rng.uniform(size=(10, 4)).astype(np.float32)

        result = cluster(embeddings, min_cluster_size=20, min_samples=10)

        assert result.n_clusters == 0
        assert result.membership is None

    def test_single_cluster_membership_shape(self):
        rng = np.random.default_rng(7)
        tight = rng.normal(loc=0.0, scale=0.01, size=(30, 4)).astype(np.float32)

        result = cluster(tight, min_cluster_size=5, min_samples=2)

        assert result.n_clusters >= 1
        if result.membership is not None:
            assert result.membership.shape[0] == 30

    def test_fewer_than_two_points_raises(self):
        with pytest.raises(ValueError, match="at least 2 points"):
            cluster(np.array([[1.0, 2.0]], dtype=np.float32), min_cluster_size=2, min_samples=1)

    def test_extra_kwargs_ignored(self):
        rng = np.random.default_rng(42)
        embeddings = rng.normal(size=(20, 4)).astype(np.float32)
        result = cluster(
            embeddings,
            min_cluster_size=3,
            min_samples=2,
            unknown_future_param=True,
        )
        assert isinstance(result, SoftClusterResult)
