"""
Component tests for backend/api/movies.py.

Uses the shared db_url fixture (testcontainers + isolated schema).
Catalogue rows are seeded with real embeddings so vector similarity is meaningful.
"""

import psycopg
import pytest

from backend.api.movies import fetch_metadata, vector_search
from db.ingestion.embed import encode_all


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

_CATALOGUE = [
    {
        "id": 10001,
        "title": "Rebel Space Odyssey",
        "overview": "A band of rebels fights an oppressive galactic empire across distant star systems.",
        "genres": [("genre_1001", "Science Fiction"), ("genre_1002", "Action")],
        "person_id": 20001,
        "director": "Lucas Test",
    },
    {
        "id": 10002,
        "title": "Paris in Love",
        "overview": "Two strangers fall in love on the rainy streets of Paris and discover life together.",
        "genres": [("genre_1003", "Romance"), ("genre_1004", "Drama")],
        "person_id": 20002,
        "director": "Sophie Test",
    },
    {
        "id": 10003,
        "title": "The Trenches",
        "overview": "Soldiers face brutal trench warfare on the Western Front in the First World War.",
        "genres": [("genre_1005", "War"), ("genre_1004", "Drama")],
        "person_id": 20003,
        "director": "Kubrick Test",
    },
]


def _seed_movies(conn: psycopg.Connection) -> None:
    """Insert minimal catalogue rows with real sentence-transformer embeddings."""
    overviews = [r["overview"] for r in _CATALOGUE]
    embeddings = encode_all(overviews)

    for row, emb in zip(_CATALOGUE, embeddings):
        conn.execute(
            """
            INSERT INTO movies (id, title, overview, embedding)
            VALUES (%s, %s, %s, %s::vector)
            ON CONFLICT (id) DO UPDATE SET
              title=EXCLUDED.title, overview=EXCLUDED.overview, embedding=EXCLUDED.embedding
            """,
            (row["id"], row["title"], row["overview"], emb.tolist()),
        )

    seen_genres: set[str] = set()
    for row in _CATALOGUE:
        for genre_key, genre_name in row["genres"]:
            if genre_key not in seen_genres:
                seen_genres.add(genre_key)
                genre_id = int(genre_key.split("_")[1])
                conn.execute(
                    "INSERT INTO genres (id, name) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name",
                    (genre_id, genre_name),
                )

    for row in _CATALOGUE:
        for genre_key, _ in row["genres"]:
            genre_id = int(genre_key.split("_")[1])
            conn.execute(
                "INSERT INTO movie_genres (movie_id, genre_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (row["id"], genre_id),
            )

    seen_people: set[int] = set()
    for row in _CATALOGUE:
        pid = row["person_id"]
        if pid not in seen_people:
            seen_people.add(pid)
            conn.execute(
                "INSERT INTO people (id, name, gender) VALUES (%s, %s, 0) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name",
                (pid, row["director"]),
            )
        conn.execute(
            "INSERT INTO crew_members (movie_id, person_id, department, job, credit_id)"
            " VALUES (%s, %s, 'Directing', 'Director', %s)"
            " ON CONFLICT (movie_id, person_id, credit_id) DO NOTHING",
            (row["id"], pid, f"cr_{row['id']}"),
        )

    conn.commit()


# Lazily seed once per test (db_url gives a fresh schema per test).
@pytest.fixture()
def seeded_db(db_url, db_conn):
    _seed_movies(db_conn)
    return db_url


# ---------------------------------------------------------------------------
# vector_search
# ---------------------------------------------------------------------------

class TestVectorSearch:
    def test_returns_top_k_hits(self, seeded_db):
        query_emb = encode_all(["space opera with rebels fighting an empire"])[0]
        hits = vector_search(query_emb, k=3)

        assert len(hits) == 3
        assert hits[0].movie_id == 10001, "Rebel Space Odyssey should be most similar"

    def test_scores_are_descending(self, seeded_db):
        query_emb = encode_all(["romantic drama set in Europe"])[0]
        hits = vector_search(query_emb, k=3)

        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)

    def test_k_limits_results(self, seeded_db):
        query_emb = encode_all(["war film"])[0]
        hits = vector_search(query_emb, k=1)

        assert len(hits) == 1

    def test_scores_bounded(self, seeded_db):
        query_emb = encode_all(["movie"])[0]
        hits = vector_search(query_emb, k=3)

        for h in hits:
            assert -0.01 <= h.score <= 1.01, f"score {h.score} out of expected range"

    def test_k_zero_raises(self, seeded_db):
        query_emb = encode_all(["test"])[0]
        with pytest.raises(ValueError, match="k must be positive"):
            vector_search(query_emb, k=0)

    def test_k_larger_than_catalogue_returns_all(self, seeded_db):
        query_emb = encode_all(["film"])[0]
        hits = vector_search(query_emb, k=1000)

        assert len(hits) == len(_CATALOGUE)


# ---------------------------------------------------------------------------
# fetch_metadata
# ---------------------------------------------------------------------------

class TestFetchMetadata:
    def test_returns_requested_movies(self, seeded_db):
        metas = fetch_metadata([10001, 10002])

        assert len(metas) == 2
        assert {m.movie_id for m in metas} == {10001, 10002}

    def test_preserves_order(self, seeded_db):
        metas = fetch_metadata([10003, 10001])

        assert metas[0].movie_id == 10003
        assert metas[1].movie_id == 10001

    def test_enriched_fields(self, seeded_db):
        metas = fetch_metadata([10001])
        m = metas[0]

        assert m.title == "Rebel Space Odyssey"
        assert "Science Fiction" in m.genres
        assert m.director == "Lucas Test"
        assert "rebel" in (m.overview or "").lower()

    def test_empty_input_returns_empty(self, seeded_db):
        result = fetch_metadata([])
        assert result == []

    def test_missing_id_silently_dropped(self, seeded_db):
        metas = fetch_metadata([10001, 99999])

        assert len(metas) == 1
        assert metas[0].movie_id == 10001
