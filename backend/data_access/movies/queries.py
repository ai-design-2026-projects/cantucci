import logging
from typing import Union

import numpy as np

from backend.data_access.connection import transaction
from backend.data_access.movies.types import MovieDetailsRow, MovieRow, MovieSearchHit, MovieStubRow
from backend.settings import get_settings

log = logging.getLogger(__name__)

_TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w500"


def vector_search(
    embedding: Union[list[float], "np.ndarray"],
    k: int,
    exclude_ids: list[int] | None = None,
) -> list[MovieSearchHit]:
    """Return top-k movies ordered by cosine similarity to *embedding* using fused_embedding.

    Args:
        embedding:   Query vector of dimension 1024.
        k:           Maximum number of results to return.
        exclude_ids: Movie IDs to omit from results.

    Returns:
        List of ``MovieSearchHit`` ordered by descending similarity.

    Raises:
        ValueError: If *k* is not a positive integer.
    """
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")

    vec = embedding.tolist() if isinstance(embedding, np.ndarray) else list(embedding)
    probes = get_settings().retrieval.ivfflat_probes

    with transaction() as conn:
        conn.execute(f"SET LOCAL ivfflat.probes = {int(probes)}")
        if exclude_ids:
            rows = conn.execute(
                """
                SELECT id, title, 1 - (fused_embedding <=> %s::vector) AS score
                FROM movies
                WHERE fused_embedding IS NOT NULL
                  AND id <> ALL(%s)
                ORDER BY fused_embedding <=> %s::vector
                LIMIT %s
                """,
                (vec, exclude_ids, vec, k),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, title, 1 - (fused_embedding <=> %s::vector) AS score
                FROM movies
                WHERE fused_embedding IS NOT NULL
                ORDER BY fused_embedding <=> %s::vector
                LIMIT %s
                """,
                (vec, vec, k),
            ).fetchall()

    hits = [MovieSearchHit(movie_id=r[0], title=r[1], score=float(r[2])) for r in rows]
    log.debug("vector_search", extra={"k": k, "returned": len(hits), "n_excluded": len(exclude_ids) if exclude_ids else 0})
    return hits


def fetch_fused_embeddings(movie_ids: list[int]) -> dict[int, list[float]]:
    """Return fused_embedding vectors keyed by movie_id.

    Args:
        movie_ids: TMDB integer IDs to look up.

    Returns:
        Dict mapping movie_id → 1024-dim list of floats. Missing IDs are omitted.
    """
    if not movie_ids:
        return {}

    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, fused_embedding FROM movies WHERE id = ANY(%s) AND fused_embedding IS NOT NULL",
            (movie_ids,),
        ).fetchall()

    result: dict[int, list[float]] = {}
    for row_id, emb in rows:
        result[row_id] = list(emb) if not isinstance(emb, list) else emb

    log.debug("fetch_fused_embeddings", extra={"requested": len(movie_ids), "returned": len(result)})
    return result


def fetch_metadata(movie_ids: list[int]) -> list[MovieRow]:
    """Return enriched metadata for each movie in *movie_ids*.

    Args:
        movie_ids: TMDB integer IDs to look up.

    Returns:
        List of ``MovieRow`` in the same order as *movie_ids*, with missing IDs dropped.
    """
    if not movie_ids:
        return []

    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                m.id,
                m.title,
                m.overview,
                m.tagline,
                m.release_year,
                COALESCE(
                    ARRAY_AGG(DISTINCT g.name) FILTER (WHERE g.name IS NOT NULL),
                    '{}'
                ) AS genres,
                (
                    SELECT p.name
                    FROM crew_members cm2
                    JOIN people p ON p.id = cm2.person_id
                    WHERE cm2.movie_id = m.id AND cm2.job = 'Director'
                    LIMIT 1
                ) AS director
            FROM movies m
            LEFT JOIN movie_genres mg ON mg.movie_id = m.id
            LEFT JOIN genres g ON g.id = mg.genre_id
            WHERE m.id = ANY(%s)
            GROUP BY m.id, m.title, m.overview, m.tagline, m.release_year
            """,
            (movie_ids,),
        ).fetchall()

    by_id: dict[int, MovieRow] = {
        r[0]: MovieRow(
            movie_id=r[0],
            title=r[1],
            overview=r[2],
            tagline=r[3],
            release_year=r[4],
            genres=list(r[5]) if r[5] else [],
            director=r[6],
        )
        for r in rows
    }
    result = [by_id[mid] for mid in movie_ids if mid in by_id]
    log.debug("fetch_metadata", extra={"requested": len(movie_ids), "returned": len(result)})
    return result


def fetch_stubs(movie_ids: list[int]) -> list[MovieStubRow]:
    """Return lightweight movie stubs (id, title, poster_url, release_year, vote_average).

    Args:
        movie_ids: TMDB integer IDs to look up.

    Returns:
        List of ``MovieStubRow`` in the same order as *movie_ids*, with missing IDs dropped.
    """
    if not movie_ids:
        return []

    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, title, poster_path, release_year, vote_average FROM movies WHERE id = ANY(%s)",
            (movie_ids,),
        ).fetchall()

    by_id = {
        r[0]: MovieStubRow(
            id=r[0],
            title=r[1],
            poster_url=f"{_TMDB_POSTER_BASE}{r[2]}" if r[2] else None,
            release_year=r[3],
            vote_average=r[4],
        )
        for r in rows
    }
    result = [by_id[mid] for mid in movie_ids if mid in by_id]
    log.debug("fetch_stubs", extra={"requested": len(movie_ids), "returned": len(result)})
    return result


def fetch_movie_details(movie_ids: list[int]) -> list[MovieDetailsRow]:
    """Return full movie details including genres, director, and top cast.

    Args:
        movie_ids: TMDB integer IDs to look up.

    Returns:
        List of ``MovieDetailsRow`` in the same order as *movie_ids*, with missing IDs dropped.
    """
    if not movie_ids:
        return []

    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                m.id,
                m.title,
                m.release_year,
                m.runtime,
                m.vote_average,
                m.vote_count,
                m.bayesian_rating,
                m.overview,
                m.poster_path,
                m.original_language,
                COALESCE(
                    ARRAY_AGG(DISTINCT g.name ORDER BY g.name)
                        FILTER (WHERE g.name IS NOT NULL),
                    '{}'
                ) AS genres,
                (
                    SELECT p.name
                    FROM crew_members cm2
                    JOIN people p ON p.id = cm2.person_id
                    WHERE cm2.movie_id = m.id AND cm2.job = 'Director'
                    LIMIT 1
                ) AS director,
                ARRAY(
                    SELECT p.name
                    FROM cast_members cm3
                    JOIN people p ON p.id = cm3.person_id
                    WHERE cm3.movie_id = m.id
                    ORDER BY cm3.cast_order NULLS LAST
                    LIMIT 3
                ) AS top_cast
            FROM movies m
            LEFT JOIN movie_genres mg ON mg.movie_id = m.id
            LEFT JOIN genres g ON g.id = mg.genre_id
            WHERE m.id = ANY(%s)
            GROUP BY m.id
            """,
            (movie_ids,),
        ).fetchall()

    by_id: dict[int, MovieDetailsRow] = {
        r[0]: MovieDetailsRow(
            id=r[0],
            title=r[1],
            release_year=r[2],
            runtime=r[3],
            vote_average=r[4],
            vote_count=r[5],
            bayesian_rating=r[6],
            overview=r[7],
            poster_url=(f"{_TMDB_POSTER_BASE}{r[8]}" if r[8] else None),
            original_language=r[9],
            genres=list(r[10]) if r[10] else [],
            director=r[11],
            top_cast=list(r[12]) if r[12] else [],
        )
        for r in rows
    }
    result = [by_id[mid] for mid in movie_ids if mid in by_id]
    log.debug("fetch_movie_details", extra={"requested": len(movie_ids), "returned": len(result)})
    return result
