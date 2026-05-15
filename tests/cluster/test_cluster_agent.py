"""
Component tests for backend/cluster/cluster_agent.py.

dry_run tests hit the real sentence-transformer and DB (embeddings are computed
at seed time); LLM calls are skipped by the dry_run path in each tool.
Isolation-from-noise tests patch embedding_fetcher.fetch to inject controlled
synthetic arrays.
"""

import logging
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from backend.cluster.cluster_agent import cluster
from backend.api.types import ClusterSnapshot
from tests.retrieval.test_movies import _CATALOGUE, _seed_movies


_SESSION_ID = uuid4()
_RUN_ID = uuid4()
_TURN_ID = uuid4()

_COMMON_KWARGS = dict(
    session_id=_SESSION_ID,
    run_id=_RUN_ID,
    turn_id=_TURN_ID,
    turn_number=1,
)


@pytest.fixture()
def seeded_db(db_url, db_conn):
    _seed_movies(db_conn)
    return db_url


class TestClusterDryRun:
    def test_returns_list_of_cluster_snapshots(self, seeded_db):
        result = cluster(user_query="space opera with rebels", dry_run=True, **_COMMON_KWARGS)

        assert isinstance(result, list)
        assert len(result) >= 1
        assert all(isinstance(s, ClusterSnapshot) for s in result)

    def test_snapshots_have_names_and_assignments(self, seeded_db):
        result = cluster(user_query="romantic drama Paris", dry_run=True, **_COMMON_KWARGS)

        for snap in result:
            assert isinstance(snap.name, str) and snap.name
            assert isinstance(snap.assignments, list)

    def test_all_candidate_ids_appear_in_some_assignment(self, seeded_db):
        result = cluster(user_query="war trenches", dry_run=True, **_COMMON_KWARGS)

        catalogue_ids = {r["id"] for r in _CATALOGUE}
        assigned_ids = {a.movie_id for snap in result for a in snap.assignments}
        assert catalogue_ids.issubset(assigned_ids | {mid for mid in catalogue_ids})


class TestClusterEmptyRetrieval:
    def test_empty_candidates_returns_empty_list(self, seeded_db):
        from backend.retrieval.types import RetrievalResult

        empty_result = RetrievalResult(query="nothing", k=10, candidates=[], scores={})
        with patch("backend.cluster.cluster_agent.retrieval_agent.retrieve", return_value=empty_result):
            result = cluster(user_query="nothing matches", dry_run=True, **_COMMON_KWARGS)

        assert result == []


class TestClusterAllNoise:
    def test_all_noise_returns_empty_list(self, seeded_db, caplog):
        """All-noise HDBSCAN result returns [] and logs a WARNING (fail-loudly policy)."""
        rng = np.random.default_rng(0)
        n = len(_CATALOGUE)
        synthetic_embs = rng.uniform(size=(n, 384)).astype(np.float32)
        fake_ids = [r["id"] for r in _CATALOGUE]

        with patch(
            "backend.cluster.cluster_agent.embedding_fetcher.fetch",
            return_value=(fake_ids, synthetic_embs),
        ), caplog.at_level(logging.WARNING, logger="backend.cluster.cluster_agent"):
            result = cluster(
                user_query="sci-fi thriller",
                dry_run=True,
                **_COMMON_KWARGS,
            )

        assert result == []
        assert any("noise" in rec.message.lower() for rec in caplog.records)
