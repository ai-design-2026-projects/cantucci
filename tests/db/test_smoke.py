"""DB layer smoke tests.

Goal: prove the migration + ingestion pipeline produces a queryable mini
catalogue with the expected schema, vector index, and similarity-search wiring.
No algorithm-level assertions; this is a connection check, not a quality check.
"""

from __future__ import annotations

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from backend.settings import MIGRATIONS_DIR, get_settings


def test_migrations_recorded(db_url: str, mini_catalogue: int) -> None:
    """schema_migrations holds one row per .sql file in db/migrations/."""
    expected = len(list(MIGRATIONS_DIR.glob("*.sql")))
    with psycopg.connect(db_url) as conn:
        applied = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
    assert applied is not None
    assert applied[0] == expected


def test_movies_have_expected_embedding_dim(db_url: str, mini_catalogue: int) -> None:
    """Every embedding column has the dimensionality declared in the active config."""
    expected_dim = get_settings().representation.embedding_dim
    with psycopg.connect(db_url) as conn:
        register_vector(conn)
        rows = conn.execute(
            "SELECT embedding FROM movies WHERE embedding IS NOT NULL LIMIT 5"
        ).fetchall()
    assert rows, "expected at least one row with an embedding"
    for (vec,) in rows:
        assert len(vec) == expected_dim


def test_vector_index_exists(db_url: str, mini_catalogue: int) -> None:
    """The ivfflat cosine index on movies.embedding is present."""
    with psycopg.connect(db_url) as conn:
        idx = conn.execute(
            """
            SELECT indexdef FROM pg_indexes
            WHERE tablename = 'movies' AND indexdef ILIKE '%ivfflat%'
            """
        ).fetchall()
    assert idx, "expected an ivfflat index on movies.embedding"


def test_vector_similarity_query_runs(db_url: str, mini_catalogue: int) -> None:
    """A cosine-distance query against the embedding column returns ordered rows."""
    dim = get_settings().representation.embedding_dim
    probe = np.zeros(dim, dtype=np.float32)
    probe[0] = 1.0
    with psycopg.connect(db_url) as conn:
        register_vector(conn)
        rows = conn.execute(
            "SELECT id, embedding <=> %s AS distance FROM movies ORDER BY distance LIMIT 5",
            (probe,),
        ).fetchall()
    assert len(rows) == 5
    distances = [r[1] for r in rows]
    assert distances == sorted(distances)
