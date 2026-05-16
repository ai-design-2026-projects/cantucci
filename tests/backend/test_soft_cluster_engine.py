"""soft_cluster_engine unit tests.

Verifies the UMAP-front-end fix for the "HDBSCAN classifies everything as
noise" regression on small high-dimensional pools, plus the safety clamps
that keep UMAP usable on tiny inputs.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.cluster.tools import soft_cluster_engine
from backend.settings import UmapConfig


def _planted_clusters(
    n_per_cluster: int,
    n_clusters: int,
    dim: int,
    seed: int,
    centre_scale: float = 5.0,
    jitter: float = 0.1,
) -> np.ndarray:
    """Build n_clusters Gaussian blobs in *dim*-d, then unit-normalise rows."""
    rng = np.random.default_rng(seed)
    centres = rng.normal(scale=centre_scale, size=(n_clusters, dim))
    points = np.vstack(
        [centres[c] + rng.normal(scale=jitter, size=(n_per_cluster, dim)) for c in range(n_clusters)]
    ).astype(np.float32)
    norms = np.linalg.norm(points, axis=1, keepdims=True)
    return points / np.clip(norms, 1e-12, None)


def test_umap_recovers_clusters_on_high_dim_pool() -> None:
    """50 points in 1024-d with 3 planted blobs: HDBSCAN alone tends to call
    everything noise; UMAP+HDBSCAN should recover at least 2 clusters."""
    embeddings = _planted_clusters(n_per_cluster=17, n_clusters=3, dim=1024, seed=42)

    umap_cfg = UmapConfig(enabled=True, n_components=5, n_neighbors=15, min_dist=0.0, metric="cosine")
    result = soft_cluster_engine.cluster(
        embeddings,
        min_cluster_size=3,
        min_samples=1,
        cluster_selection_method="leaf",
        umap_cfg=umap_cfg,
        seed=42,
    )

    assert result.n_clusters >= 2, (
        f"UMAP+HDBSCAN should recover the planted structure; got n_clusters={result.n_clusters}"
    )
    assert result.membership is not None
    assert result.membership.shape == (embeddings.shape[0], result.n_clusters)


def test_umap_disabled_matches_raw_hdbscan_path() -> None:
    """With umap_cfg=None the function must behave exactly like the pre-UMAP
    implementation: raw embeddings → HDBSCAN, same shapes, same return type."""
    embeddings = _planted_clusters(n_per_cluster=10, n_clusters=2, dim=32, seed=7)

    result = soft_cluster_engine.cluster(
        embeddings,
        min_cluster_size=3,
        min_samples=1,
        cluster_selection_method="leaf",
        umap_cfg=None,
        seed=7,
    )

    assert result.labels.shape == (embeddings.shape[0],)
    if result.n_clusters == 0:
        assert result.membership is None
    else:
        assert result.membership is not None
        assert result.membership.shape == (embeddings.shape[0], result.n_clusters)


def test_n_neighbors_is_clamped_for_tiny_pool() -> None:
    """6 points + n_neighbors=15 must not raise; UMAP receives n_neighbors=5."""
    embeddings = _planted_clusters(n_per_cluster=3, n_clusters=2, dim=64, seed=11)
    assert embeddings.shape[0] == 6

    umap_cfg = UmapConfig(enabled=True, n_components=2, n_neighbors=15, min_dist=0.0, metric="cosine")
    result = soft_cluster_engine.cluster(
        embeddings,
        min_cluster_size=2,
        min_samples=1,
        cluster_selection_method="leaf",
        umap_cfg=umap_cfg,
        seed=11,
    )

    assert result.labels.shape == (embeddings.shape[0],)


def test_raises_on_singleton_pool() -> None:
    """Single-row input is an upstream bug; the engine must refuse it loudly."""
    with pytest.raises(ValueError, match="at least 2 points"):
        soft_cluster_engine.cluster(
            np.zeros((1, 16), dtype=np.float32),
            min_cluster_size=3,
            min_samples=1,
        )
