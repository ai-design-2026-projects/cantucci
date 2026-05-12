"""
Component tests for backend/retrieval/agent.py.

Uses the shared seeded_db fixture from test_movies (conftest re-export) via
direct import of the helper. Each test gets an isolated schema with 3 seeded
films (sci-fi, romance, war) so semantic ranking is meaningful.
"""

import pytest

from backend.retrieval.agent import retrieve
from tests.retrieval.test_movies import _CATALOGUE, _seed_movies


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_db(db_url, db_conn):
    _seed_movies(db_conn)
    return db_url


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------

class TestRetrieve:
    def test_returns_retrieval_result(self, seeded_db):
        result = retrieve(query="space opera with rebels", k=3)

        assert result.query == "space opera with rebels"
        assert result.k == 3
        assert len(result.candidates) == 3

    def test_top_result_is_scifi(self, seeded_db):
        result = retrieve(query="galactic rebels fighting an empire in space", k=3)

        assert result.candidates[0].movie_id == 10001

    def test_scores_populated(self, seeded_db):
        result = retrieve(query="romantic drama", k=3)

        for candidate in result.candidates:
            assert candidate.movie_id in result.scores
            assert isinstance(result.scores[candidate.movie_id], float)

    def test_candidates_ordered_by_score(self, seeded_db):
        result = retrieve(query="war film trench", k=3)

        scores = [result.scores[c.movie_id] for c in result.candidates]
        assert scores == sorted(scores, reverse=True)

    def test_metadata_enriched(self, seeded_db):
        result = retrieve(query="space opera", k=1)

        c = result.candidates[0]
        assert c.title is not None
        assert isinstance(c.genres, list)

    def test_k_smaller_than_catalogue(self, seeded_db):
        result = retrieve(query="film", k=1)

        assert len(result.candidates) == 1
        assert len(result.scores) == 1

    def test_k_larger_than_catalogue(self, seeded_db):
        result = retrieve(query="film", k=100)

        assert len(result.candidates) == len(_CATALOGUE)

    def test_constraints_ignored_with_warning(self, seeded_db, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="backend.retrieval.agent"):
            result = retrieve(
                query="space film",
                k=2,
                active_constraints={"exclude_genres": ["Horror"]},
            )

        assert len(result.candidates) > 0
        assert any("active_constraints" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestRetrieveValidation:
    def test_empty_query_raises(self, db_url):
        with pytest.raises(ValueError, match="non-empty"):
            retrieve(query="", k=5)

    def test_whitespace_query_raises(self, db_url):
        with pytest.raises(ValueError, match="non-empty"):
            retrieve(query="   ", k=5)

    def test_k_zero_raises(self, db_url):
        with pytest.raises(ValueError, match="k must be positive"):
            retrieve(query="film", k=0)

    def test_k_negative_raises(self, db_url):
        with pytest.raises(ValueError, match="k must be positive"):
            retrieve(query="film", k=-1)
