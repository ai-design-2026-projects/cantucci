"""Read-only catalogue queries: vector search, metadata enrichment, and embedding fetch.

``vector_search`` and ``fetch_metadata`` are called by the Retrieval System tools
(backend/retrieval/tools/).  ``fetch_embeddings`` is called exclusively by the
Cluster Agent embedding_fetcher tool (backend/cluster/tools/embedding_fetcher.py).
No other modules should call these directly.
"""

import logging
from typing import Union

import numpy as np

from backend.api.db import transaction
from backend.api.types import MovieHit, MovieMetadata

log = logging.getLogger(__name__)


def vector_search(
    embedding: Union[list[float], "np.ndarray"],  # type: ignore[type-arg]
    k: int,
    exclude_ids: list[int] | None = None,
) -> list[MovieHit]:
    """Return top-k films ordered by cosine similarity to *embedding*.

    The pgvector ``<=>`` operator computes cosine distance; similarity is
    ``1 - distance`` so the list is descending by relevance.

    Args:
        embedding:   Query vector of dimension 384 (must match movies.embedding).
        k:           Maximum number of results to return.
        exclude_ids: Optional list of movie_ids to omit from the result set. The
                     filter is applied in SQL (``id <> ALL(...)``) so the LIMIT
                     still yields up to *k* rows after exclusion. ``None`` or
                     ``[]`` skips the filter entirely.

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

    with transaction() as conn:
        if exclude_ids:
            rows = conn.execute(
                """
                SELECT id, title, 1 - (embedding <=> %s::vector) AS score
                FROM movies
                WHERE id <> ALL(%s)
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vec, exclude_ids, vec, k),
            ).fetchall()
        else:
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
        extra={
            "k": k,
            "returned": len(hits),
            "top_score": hits[0].score if hits else None,
            "n_excluded": len(exclude_ids) if exclude_ids else 0,
        },
    )
    return hits


def resolve_titles_to_ids(titles: list[str]) -> list[int]:
    """Fuzzy-match *titles* against ``movies.title`` and return the union of matching IDs.

    Each input string becomes an ``ILIKE '%<title>%'`` predicate, so series or
    franchise stems expand to every catalogue entry whose title contains them
    (``"Lord of the Rings"`` → all three films, ``"Spider-Man"`` → every
    Spider-Man release).  Matching is case-insensitive.  An optional leading
    ``"The "`` is stripped from each input so utterances like ``"The Dark Knight"``
    still match titles stored without the article.

    Titles that match nothing are simply absent from the returned list — the
    LLM can hallucinate or mis-spell titles and that is not an error condition
    for the retrieval pipeline. The miss is logged at INFO so the noise stays
    visible in dev.

    Args:
        titles: List of film titles or series roots emitted by the reformulator.

    Returns:
        Deduplicated list of catalogue ``movie_id`` values matching any input
        title; empty list when *titles* is empty.
    """
    if not titles:
        return []

    patterns: list[str] = []
    for raw in titles:
        cleaned = raw.strip()
        if not cleaned:
            continue
        if cleaned.lower().startswith("the "):
            cleaned = cleaned[4:]
        patterns.append(f"%{cleaned}%")

    if not patterns:
        return []

    with transaction() as conn:
        rows = conn.execute(
            "SELECT DISTINCT id FROM movies WHERE title ILIKE ANY(%s)",
            (patterns,),
        ).fetchall()

    ids = [r[0] for r in rows]
    if not ids:
        log.info(
            "resolve_titles_to_ids: no matches",
            extra={"titles": titles},
        )
    else:
        log.debug(
            "resolve_titles_to_ids",
            extra={"titles": titles, "n_matched": len(ids)},
        )
    return ids


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


def fetch_stubs(movie_ids: list[int]) -> list[dict]:
    """Return lightweight movie stubs for cluster snapshot payloads.

    Fetches only the fields needed for ``ClusterFilmStub``: id, title,
    poster_url (built from poster_path), release_year, and vote_average.
    Missing IDs are silently omitted.

    Args:
        movie_ids: TMDB integer IDs to look up.

    Returns:
        List of dicts with keys ``id``, ``title``, ``poster_url``,
        ``release_year``, ``vote_average``.  Order matches *movie_ids*.
    """
    if not movie_ids:
        return []

    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, title, poster_path, release_year, vote_average
            FROM movies
            WHERE id = ANY(%s)
            """,
            (movie_ids,),
        ).fetchall()

    tmdb_base = "https://image.tmdb.org/t/p/w500"
    by_id = {
        r[0]: {
            "id": r[0],
            "title": r[1],
            "poster_url": f"{tmdb_base}{r[2]}" if r[2] else None,
            "release_year": r[3],
            "vote_average": r[4],
        }
        for r in rows
    }
    result = [by_id[mid] for mid in movie_ids if mid in by_id]
    log.debug("fetch_stubs", extra={"requested": len(movie_ids), "returned": len(result)})
    return result


def fetch_embeddings(movie_ids: list[int]) -> dict[int, list[float]]:
    """Return raw embeddings keyed by movie_id for the given IDs.

    Missing IDs are silently omitted — callers must check the returned dict
    against the requested list if order or completeness matters.

    Args:
        movie_ids: TMDB integer IDs to look up.

    Returns:
        Dict mapping movie_id → 384-dim embedding as a list of floats.
    """
    if not movie_ids:
        return {}

    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, embedding::text FROM movies WHERE id = ANY(%s)",
            (movie_ids,),
        ).fetchall()

    result: dict[int, list[float]] = {}
    for row_id, emb_text in rows:
        floats = [float(x) for x in emb_text.strip("[]").split(",")]
        result[row_id] = floats

    log.debug(
        "fetch_embeddings",
        extra={"requested": len(movie_ids), "returned": len(result)},
    )
    return result
