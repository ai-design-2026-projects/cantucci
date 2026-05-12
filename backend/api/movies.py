"""Read-only catalogue queries: vector search and metadata enrichment.

Both functions are called exclusively by the Retrieval System tools
(backend/retrieval/tools/). No other module should call these directly.
"""

import logging
from typing import Union

import numpy as np

from backend.api.db import tx
from backend.models.movies import MovieHit, MovieMetadata

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
