import logging
from typing import Union

import numpy as np

from backend.data_access.connection import transaction
from backend.data_access.movies.types import ClusterProfileRow, MovieDetailsRow, MovieRow, MovieSearchHitRow, MovieStubRow, NumericStats
from backend.settings import get_settings

_MODALITY_COLUMN: dict[str, str] = {
    "text": "text_embedding",
    "review": "review_embedding",
    "trailer": "trailer_embedding",
}

log = logging.getLogger(__name__)


def list_movie_ids() -> list[int]:
    """Return all movie IDs in the catalogue, ordered by ID.

    Returns:
        List of TMDB integer IDs.
    """
    with transaction() as conn:
        rows = conn.execute("SELECT id FROM movies ORDER BY id").fetchall()
    return [r["id"] for r in rows]


def vector_search(
    embedding: Union[list[float], "np.ndarray"],
    k: int,
    exclude_ids: list[int] | None = None,
) -> list[MovieSearchHitRow]:
    """Return top-k movies ordered by cosine similarity to *embedding* using text_embedding.

    Searches the BGE text embedding space. Use this for text-driven queries
    such as title resolution or semantic similarity by description.

    Args:
        embedding:   BGE query vector of dimension 1024.
        k:           Maximum number of results to return.
        exclude_ids: Movie IDs to omit from results.

    Returns:
        List of ``MovieSearchHitRow`` ordered by descending similarity.

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
                SELECT id, title, 1 - (text_embedding <=> %s::vector) AS score
                FROM movies
                WHERE text_embedding IS NOT NULL
                  AND id <> ALL(%s)
                ORDER BY text_embedding <=> %s::vector
                LIMIT %s
                """,
                (vec, exclude_ids, vec, k),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, title, 1 - (text_embedding <=> %s::vector) AS score
                FROM movies
                WHERE text_embedding IS NOT NULL
                ORDER BY text_embedding <=> %s::vector
                LIMIT %s
                """,
                (vec, vec, k),
            ).fetchall()

    hits = [MovieSearchHitRow.from_row(r) for r in rows]
    log.debug("vector_search", extra={"k": k, "returned": len(hits), "n_excluded": len(exclude_ids) if exclude_ids else 0})
    return hits


def fetch_text_embeddings(movie_ids: list[int]) -> dict[int, list[float]]:
    """Return text_embedding vectors keyed by movie_id.

    Args:
        movie_ids: TMDB integer IDs to look up.

    Returns:
        Dict mapping movie_id → 1024-dim list of floats. Missing IDs are omitted.
    """
    if not movie_ids:
        return {}

    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, text_embedding FROM movies WHERE id = ANY(%s) AND text_embedding IS NOT NULL",
            (movie_ids,),
        ).fetchall()

    result: dict[int, list[float]] = {}
    for r in rows:
        emb = r["text_embedding"]
        result[r["id"]] = list(emb) if not isinstance(emb, list) else emb

    log.debug("fetch_text_embeddings", extra={"requested": len(movie_ids), "returned": len(result)})
    return result


def fetch_modality_embeddings(
    movie_ids: list[int],
    modalities: list[str],
) -> dict[str, dict[int, np.ndarray]]:
    """Return per-modality embedding arrays keyed by movie_id.

    Fetches all requested modality columns in a single SQL pass and returns
    only movies that have a non-null value for every requested modality.

    Valid modality names: ``"text"``, ``"review"``, ``"trailer"``.

    Args:
        movie_ids:  TMDB integer IDs to look up.
        modalities: Modality names to fetch.

    Returns:
        Dict mapping modality name → ``{movie_id: np.ndarray}``. Only movie
        IDs present in all requested modalities are included in each sub-dict.

    Raises:
        ValueError: If *modalities* is empty or contains an unknown name.
    """
    if not modalities:
        raise ValueError("modalities must not be empty")
    unknown = [m for m in modalities if m not in _MODALITY_COLUMN]
    if unknown:
        raise ValueError(f"Unknown modalities: {unknown}. Valid: {list(_MODALITY_COLUMN)}")
    if not movie_ids:
        return {m: {} for m in modalities}

    cols = [_MODALITY_COLUMN[m] for m in modalities]
    null_checks = " AND ".join(f"{c} IS NOT NULL" for c in cols)
    select_cols = ", ".join(["id"] + cols)
    sql = f"SELECT {select_cols} FROM movies WHERE id = ANY(%s) AND {null_checks}"

    with transaction() as conn:
        rows = conn.execute(sql, (movie_ids,)).fetchall()

    result: dict[str, dict[int, np.ndarray]] = {m: {} for m in modalities}
    for r in rows:
        mid = r["id"]
        for modality, col in zip(modalities, cols):
            emb = r[col]
            result[modality][mid] = np.array(emb, dtype=np.float32)

    log.debug(
        "fetch_modality_embeddings",
        extra={"modalities": modalities, "requested": len(movie_ids), "returned": len(rows)},
    )
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

    by_id: dict[int, MovieRow] = {r["id"]: MovieRow.from_row(r) for r in rows}
    result = [by_id[mid] for mid in movie_ids if mid in by_id]
    log.debug("fetch_metadata", extra={"requested": len(movie_ids), "returned": len(result)})
    return result


def filter_movie_ids_by_metadata(
    movie_ids: list[int],
    genres: list[str] | None = None,
    release_year_min: int | None = None,
    release_year_max: int | None = None,
    director: str | None = None,
) -> list[int]:
    """Return the subset of *movie_ids* that satisfy all non-null metadata predicates.

    Predicates are combined with AND; multiple genres are combined with OR.  All
    filtering happens in SQL — never in application memory.

    Args:
        movie_ids:         Input ID universe to filter.
        genres:            Keep movies that belong to at least one of these genres.
        release_year_min:  Keep movies released in this year or later (inclusive).
        release_year_max:  Keep movies released in this year or earlier (inclusive).
        director:          Keep movies directed by someone whose name contains this
                           string (case-insensitive substring match).

    Returns:
        Filtered list of TMDB IDs preserving the input ordering.
    """
    if not movie_ids:
        return []

    conditions: list[str] = ["m.id = ANY(%s)"]
    params: list = [movie_ids]

    if genres:
        conditions.append(
            "EXISTS ("
            "SELECT 1 FROM movie_genres mg JOIN genres g ON g.id = mg.genre_id "
            "WHERE mg.movie_id = m.id AND g.name = ANY(%s)"
            ")"
        )
        params.append(genres)
    if release_year_min is not None:
        conditions.append("m.release_year >= %s")
        params.append(release_year_min)
    if release_year_max is not None:
        conditions.append("m.release_year <= %s")
        params.append(release_year_max)
    if director is not None:
        conditions.append(
            "EXISTS ("
            "SELECT 1 FROM crew_members cm JOIN people p ON p.id = cm.person_id "
            "WHERE cm.movie_id = m.id AND cm.job = 'Director' AND p.name ILIKE %s"
            ")"
        )
        params.append(f"%{director}%")

    sql = "SELECT m.id FROM movies m WHERE " + " AND ".join(conditions)

    with transaction() as conn:
        rows = conn.execute(sql, params).fetchall()

    result_set = {r["id"] for r in rows}
    result = [mid for mid in movie_ids if mid in result_set]
    log.debug(
        "filter_movie_ids_by_metadata",
        extra={"requested": len(movie_ids), "returned": len(result)},
    )
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

    by_id = {r["id"]: MovieStubRow.from_row(r) for r in rows}
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
                m.trailer_youtube_key,
                m.umap_x,
                m.umap_y,
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

    by_id: dict[int, MovieDetailsRow] = {r["id"]: MovieDetailsRow.from_row(r) for r in rows}
    result = [by_id[mid] for mid in movie_ids if mid in by_id]
    log.debug("fetch_movie_details", extra={"requested": len(movie_ids), "returned": len(result)})
    return result


def fetch_cluster_profile(movie_ids: list[int]) -> ClusterProfileRow:
    """Return aggregate metadata for a set of cluster-member movies.

    Computes mean runtime, year range, mean vote average, and the top-5 genres
    by frequency across all members in a single query. Used to supply the
    labelling agent with discriminative statistics when naming operation-produced
    clusters.

    Args:
        movie_ids: TMDB integer IDs of every member of the cluster.

    Returns:
        ``ClusterProfileRow`` with aggregated statistics. All numeric fields are
        ``None`` when *movie_ids* is empty or no matching rows exist.
    """
    if not movie_ids:
        return ClusterProfileRow(
            mean_runtime=None,
            min_year=None,
            max_year=None,
            mean_rating=None,
            top_genres=[],
        )

    with transaction() as conn:
        row = conn.execute(
            """
            SELECT
                AVG(m.runtime)       AS mean_runtime,
                MIN(m.release_year)  AS min_year,
                MAX(m.release_year)  AS max_year,
                AVG(m.vote_average)  AS mean_rating,
                COALESCE(
                    ARRAY(
                        SELECT g.name
                        FROM movie_genres mg
                        JOIN genres g ON g.id = mg.genre_id
                        WHERE mg.movie_id = ANY(%s)
                        GROUP BY g.name
                        ORDER BY COUNT(*) DESC
                        LIMIT 5
                    ),
                    ARRAY[]::text[]
                ) AS top_genres
            FROM movies m
            WHERE m.id = ANY(%s)
            """,
            (movie_ids, movie_ids),
        ).fetchone()

    if row is None:
        return ClusterProfileRow(
            mean_runtime=None,
            min_year=None,
            max_year=None,
            mean_rating=None,
            top_genres=[],
        )

    result = ClusterProfileRow.from_row(row)
    log.debug("fetch_cluster_profile", extra={"n_movies": len(movie_ids)})
    return result


_NUMERIC_STAT_COLUMNS: dict[str, str] = {
    "runtime": "runtime",
    "release_year": "release_year",
    "vote_average": "vote_average",
}


def fetch_numeric_stats(movie_ids: list[int], attribute: str) -> NumericStats:
    """Return distribution statistics for a numeric attribute over a set of movies.

    Used by the partition advisor to propose sensible bin boundaries before the
    user commits to a numeric ``partition_by`` operation.

    Args:
        movie_ids: TMDB integer IDs to aggregate over.
        attribute: One of ``"runtime"``, ``"release_year"``, ``"vote_average"``.

    Returns:
        ``NumericStats`` with min, max, 25th/50th/75th percentiles, and non-null count.

    Raises:
        ValueError: If ``attribute`` is not one of the three supported numeric attributes.
    """
    col = _NUMERIC_STAT_COLUMNS.get(attribute)
    if col is None:
        raise ValueError(f"Unsupported numeric attribute for stats: {attribute!r}")
    if not movie_ids:
        return NumericStats(min_val=None, max_val=None, p25=None, p50=None, p75=None, count=0)
    with transaction() as conn:
        row = conn.execute(
            f"""
            SELECT
                MIN({col})::float                                           AS min_val,
                MAX({col})::float                                           AS max_val,
                percentile_cont(0.25) WITHIN GROUP (ORDER BY {col})::float  AS p25,
                percentile_cont(0.50) WITHIN GROUP (ORDER BY {col})::float  AS p50,
                percentile_cont(0.75) WITHIN GROUP (ORDER BY {col})::float  AS p75,
                COUNT(*) FILTER (WHERE {col} IS NOT NULL)                   AS count
            FROM movies
            WHERE id = ANY(%s)
            """,
            (movie_ids,),
        ).fetchone()
    log.debug("fetch_numeric_stats", extra={"attribute": attribute, "n_movies": len(movie_ids)})
    return NumericStats.from_row(dict(row))


def fetch_partition_values(
    movie_ids: list[int],
    attribute: str,
) -> dict[int, list[str]] | dict[int, float | None]:
    """Return the raw metadata values for *attribute* keyed by movie ID.

    Used by the ``partition_by`` clustering operation to bucket movies by an
    exact metadata field without loading full movie rows.

    For categorical attributes (``"genre"``, ``"director"``) the value is a
    list of strings — possibly empty when the movie has no value for that
    attribute.  For numeric attributes (``"runtime"``, ``"release_year"``) the
    value is a single float or ``None`` when the column is NULL.

    Args:
        movie_ids: TMDB integer IDs to look up.
        attribute: One of ``"genre"``, ``"director"``, ``"runtime"``,
                   ``"release_year"``.

    Returns:
        Dict mapping each ID in *movie_ids* to its attribute value(s).
        Every ID in *movie_ids* is present as a key; missing DB rows produce
        an empty list (categorical) or ``None`` (numeric).

    Raises:
        ValueError: If *attribute* is not one of the four supported values.
    """
    if not movie_ids:
        return {}

    if attribute == "genre":
        with transaction() as conn:
            rows = conn.execute(
                """
                SELECT mg.movie_id,
                       ARRAY_AGG(g.name ORDER BY g.name) AS values
                FROM movie_genres mg
                JOIN genres g ON g.id = mg.genre_id
                WHERE mg.movie_id = ANY(%s)
                GROUP BY mg.movie_id
                """,
                (movie_ids,),
            ).fetchall()
        result_cat: dict[int, list[str]] = {r["movie_id"]: list(r["values"]) for r in rows}
        for mid in movie_ids:
            result_cat.setdefault(mid, [])
        log.debug("fetch_partition_values", extra={"attribute": attribute, "n_movies": len(movie_ids)})
        return result_cat

    if attribute == "director":
        with transaction() as conn:
            rows = conn.execute(
                """
                SELECT cm.movie_id,
                       ARRAY_AGG(DISTINCT p.name ORDER BY p.name) AS values
                FROM crew_members cm
                JOIN people p ON p.id = cm.person_id
                WHERE cm.movie_id = ANY(%s) AND cm.job = 'Director'
                GROUP BY cm.movie_id
                """,
                (movie_ids,),
            ).fetchall()
        result_dir: dict[int, list[str]] = {r["movie_id"]: list(r["values"]) for r in rows}
        for mid in movie_ids:
            result_dir.setdefault(mid, [])
        log.debug("fetch_partition_values", extra={"attribute": attribute, "n_movies": len(movie_ids)})
        return result_dir

    col = _NUMERIC_STAT_COLUMNS.get(attribute)
    if col is not None:
        with transaction() as conn:
            rows = conn.execute(
                f"SELECT id, {col} FROM movies WHERE id = ANY(%s)",
                (movie_ids,),
            ).fetchall()
        result_num: dict[int, float | None] = {r["id"]: r[col] for r in rows}
        for mid in movie_ids:
            result_num.setdefault(mid, None)
        log.debug("fetch_partition_values", extra={"attribute": attribute, "n_movies": len(movie_ids)})
        return result_num

    if attribute == "original_language":
        with transaction() as conn:
            rows = conn.execute(
                "SELECT id, original_language FROM movies WHERE id = ANY(%s)",
                (movie_ids,),
            ).fetchall()
        result_lang: dict[int, list[str]] = {
            r["id"]: ([r["original_language"]] if r["original_language"] else [])
            for r in rows
        }
        for mid in movie_ids:
            result_lang.setdefault(mid, [])
        log.debug("fetch_partition_values", extra={"attribute": attribute, "n_movies": len(movie_ids)})
        return result_lang


def sample_movies_for_gt(n: int, seed: int) -> list[MovieStubRow]:
    """Return a random sample of movie stubs for ground-truth trajectory building.

    Uses ``TABLESAMPLE BERNOULLI`` with a PostgreSQL seed for reproducibility.
    Falls back to ``ORDER BY random()`` when the catalogue is too small for
    TABLESAMPLE to reliably return enough rows.

    Args:
        n:    Number of movies to return.
        seed: Integer seed forwarded to ``setseed()``.

    Returns:
        List of up to *n* ``MovieStubRow`` instances.
    """
    if n <= 0:
        return []
    with transaction() as conn:
        conn.execute("SELECT setseed(%s)", (float(seed % 1000) / 1000.0,))
        rows = conn.execute(
            """
            SELECT id, title, poster_path, release_year, vote_average
            FROM movies
            ORDER BY random()
            LIMIT %s
            """,
            (n,),
        ).fetchall()
    result = [MovieStubRow.from_row(r) for r in rows]
    log.debug("sample_movies_for_gt", extra={"n_requested": n, "n_returned": len(result), "seed": seed})
    return result

    raise ValueError(f"Unsupported partition attribute: {attribute!r}")
