"""Read-only catalogue queries: vector search and metadata enrichment.

``vector_search`` and ``fetch_metadata`` are called by the Retrieval System tools.
``fetch_movies_public`` is called by the Orchestrator to build frontend payloads.
"""

import logging
from typing import Union

import numpy as np

from backend.api.db import tx
from backend.models.movies import MovieHit, MovieMetadata
from backend.models.public import MoviePublic

_TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w500"

log = logging.getLogger(__name__)


def vector_search(
    embedding: Union[list[float], "np.ndarray"],  # type: ignore[type-arg]
    k: int,
) -> list[MovieHit]:
    """Return top-k films ordered by cosine similarity to *embedding*.

    The pgvector ``<=>`` operator computes cosine distance; similarity is
    ``1 - distance`` so the list is descending by relevance.

    Args:
        embedding: Query vector of dimension 384 (must match movies.embedding).
        k:         Maximum number of results to return.

    Returns:
        List of MovieHit ordered by descending similarity. May be shorter than
        *k* if the catalogue has fewer rows.

    Raises:
        ValueError: If *k* is not a positive integer.
    """
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")

    if isinstance(embedding, np.ndarray):
        vec = embedding.tolist()
    else:
        vec = list(embedding)

    with tx() as conn:
        rows = conn.execute(
            """
            SELECT id, title, 1 - (embedding <=> %s::vector) AS score
            FROM movies
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vec, vec, k),
        ).fetchall()

    hits = [MovieHit(movie_id=r[0], title=r[1], score=float(r[2])) for r in rows]
    log.debug(
        "vector_search",
        extra={"k": k, "returned": len(hits), "top_score": hits[0].score if hits else None},
    )
    return hits


def fetch_metadata(movie_ids: list[int]) -> list[MovieMetadata]:
    """Return enriched metadata for each movie in *movie_ids*.

    Joins movies ← movie_genres → genres and crew_members (Director only).
    The return order matches the input *movie_ids* order; missing IDs are
    silently omitted (the catalogue is the authoritative source).

    Args:
        movie_ids: TMDB integer IDs to look up.

    Returns:
        List of MovieMetadata in the same order as *movie_ids*, with missing
        IDs dropped.
    """
    if not movie_ids:
        return []

    with tx() as conn:
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

    by_id: dict[int, MovieMetadata] = {
        r[0]: MovieMetadata(
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


def fetch_movies_public(movie_ids: list[int]) -> list[MoviePublic]:
    """Return full frontend-facing metadata for each movie in *movie_ids*.

    Joins movies, movie_genres, genres, crew_members (Director), and
    cast_members (top-3 billed cast).  Returns results in the same order
    as *movie_ids*; missing IDs are silently omitted.

    Args:
        movie_ids: TMDB integer IDs to look up.

    Returns:
        List of MoviePublic in *movie_ids* order, with missing IDs dropped.
    """
    if not movie_ids:
        return []

    with tx() as conn:
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
                    ARRAY_AGG(DISTINCT g.name) FILTER (WHERE g.name IS NOT NULL),
                    '{}'
                ) AS genres,
                (
                    SELECT p.name
                    FROM crew_members cm2
                    JOIN people p ON p.id = cm2.person_id
                    WHERE cm2.movie_id = m.id AND cm2.job = 'Director'
                    LIMIT 1
                ) AS director,
                COALESCE(
                    ARRAY(
                        SELECT p2.name
                        FROM cast_members cm3
                        JOIN people p2 ON p2.id = cm3.person_id
                        WHERE cm3.movie_id = m.id
                        ORDER BY cm3.cast_order ASC
                        LIMIT 3
                    ),
                    '{}'
                ) AS top_cast
            FROM movies m
            LEFT JOIN movie_genres mg ON mg.movie_id = m.id
            LEFT JOIN genres g ON g.id = mg.genre_id
            WHERE m.id = ANY(%s)
            GROUP BY m.id, m.title, m.release_year, m.runtime, m.vote_average,
                     m.vote_count, m.bayesian_rating, m.overview, m.poster_path,
                     m.original_language
            """,
            (movie_ids,),
        ).fetchall()

    by_id: dict[int, MoviePublic] = {
        r[0]: MoviePublic(
            id=r[0],
            title=r[1],
            release_year=r[2],
            runtime=r[3],
            vote_average=r[4],
            vote_count=r[5],
            bayesian_rating=r[6],
            overview=r[7],
            poster_url=f"{_TMDB_POSTER_BASE}{r[8]}" if r[8] else None,
            original_language=r[9],
            genres=list(r[10]) if r[10] else [],
            director=r[11],
            top_cast=list(r[12]) if r[12] else [],
        )
        for r in rows
    }

    result = [by_id[mid] for mid in movie_ids if mid in by_id]
    log.debug(
        "fetch_movies_public",
        extra={"requested": len(movie_ids), "returned": len(result)},
    )
    return result
