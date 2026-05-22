import logging
import numpy as np
import pandas as pd
import psycopg
import pgvector.psycopg

from backend.settings import get_env

log = logging.getLogger(__name__)


def _none(val):
    """Return None for NaN/NaT/None; pass everything else through."""
    try:
        return None if pd.isna(val) else val
    except (TypeError, ValueError):
        return val


def _upsert_genres(cur, df: pd.DataFrame) -> None:
    seen: dict[int, str] = {}
    for genres in df["genres"]:
        for g in (genres or []):
            gid = g.get("id")
            if gid is not None and gid not in seen:
                seen[int(gid)] = g.get("name", "")
    rows = list(seen.items())
    if not rows:
        return
    cur.executemany(
        "INSERT INTO genres (id, name) VALUES (%s,%s) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name",
        rows,
    )
    log.debug("genres", extra={"n": len(rows)})


def _upsert_people(cur, df: pd.DataFrame) -> None:
    seen: dict[int, str] = {}
    for col in ("cast", "crew"):
        for members in df[col]:
            for m in (members or []):
                pid = m.get("id")
                if pid is not None and pid not in seen:
                    seen[int(pid)] = m.get("name", "")
    rows = list(seen.items())
    if not rows:
        return
    cur.executemany(
        "INSERT INTO people (id, name) VALUES (%s,%s) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name",
        rows,
    )
    log.debug("people", extra={"n": len(rows)})


def _upsert_keywords(cur, df: pd.DataFrame) -> None:
    seen: dict[int, str] = {}
    for kws in df["keywords"]:
        for kw in (kws or []):
            kid = kw.get("id")
            if kid is not None and kid not in seen:
                seen[int(kid)] = kw.get("name", "")
    rows = list(seen.items())
    if not rows:
        return
    cur.executemany(
        "INSERT INTO keywords (id, name) VALUES (%s,%s) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name",
        rows,
    )
    log.debug("keywords", extra={"n": len(rows)})


def _upsert_movies(
    cur,
    df: pd.DataFrame,
    text_embeddings: np.ndarray,
    review_embeddings: np.ndarray | None,
    trailer_embeddings: np.ndarray | None = None,
) -> None:
    rows = []
    for i, (_, row) in enumerate(df.iterrows()):
        text_emb = text_embeddings[i]
        review_emb = review_embeddings[i] if review_embeddings is not None else None
        trailer_emb = trailer_embeddings[i] if trailer_embeddings is not None else None
        reviews_text = _none(row.get("reviews_text"))
        rows.append((
            int(row["id"]),
            _none(row.get("title")) or _none(row.get("original_title")),
            _none(row.get("original_title")),
            int(row["release_year"]) if pd.notna(row.get("release_year")) else None,
            float(row["runtime"]) if pd.notna(row.get("runtime")) else None,
            float(row["vote_average"]) if pd.notna(row.get("vote_average")) else None,
            int(row["vote_count"]) if pd.notna(row.get("vote_count")) else None,
            float(row["bayesian_rating"]) if pd.notna(row.get("bayesian_rating")) else None,
            _none(row.get("overview")),
            _none(row.get("tagline")),
            _none(row.get("poster_path")),
            _none(row.get("original_language")),
            _none(row.get("composite_text")),
            reviews_text,
            _none(row.get("trailer_youtube_key")),
            text_emb,
            review_emb,
            trailer_emb,
        ))
    cur.executemany(
        """
        INSERT INTO movies (
            id, title, original_title, release_year, runtime,
            vote_average, vote_count, bayesian_rating,
            overview, tagline, poster_path, original_language,
            composite_text, reviews_text, trailer_youtube_key,
            text_embedding, review_embedding, trailer_embedding
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        ON CONFLICT (id) DO UPDATE SET
            title=EXCLUDED.title, original_title=EXCLUDED.original_title,
            release_year=EXCLUDED.release_year, runtime=EXCLUDED.runtime,
            vote_average=EXCLUDED.vote_average, vote_count=EXCLUDED.vote_count,
            bayesian_rating=EXCLUDED.bayesian_rating, overview=EXCLUDED.overview,
            tagline=EXCLUDED.tagline, poster_path=EXCLUDED.poster_path,
            original_language=EXCLUDED.original_language,
            composite_text=EXCLUDED.composite_text,
            reviews_text=EXCLUDED.reviews_text,
            trailer_youtube_key=EXCLUDED.trailer_youtube_key,
            text_embedding=EXCLUDED.text_embedding,
            review_embedding=EXCLUDED.review_embedding,
            trailer_embedding=EXCLUDED.trailer_embedding
        """,
        rows,
    )
    log.info("movies upserted", extra={"n": len(rows)})


def _upsert_movie_genres(cur, df: pd.DataFrame) -> None:
    rows, seen = [], set()
    for _, row in df.iterrows():
        mid = int(row["id"])
        for g in (row["genres"] or []):
            gid = g.get("id")
            if gid is not None:
                key = (mid, int(gid))
                if key not in seen:
                    seen.add(key)
                    rows.append(key)
    if not rows:
        return
    cur.executemany(
        "INSERT INTO movie_genres (movie_id, genre_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        rows,
    )
    log.debug("movie_genres", extra={"n": len(rows)})


def _upsert_cast_members(cur, df: pd.DataFrame) -> None:
    rows, seen = [], set()
    for _, row in df.iterrows():
        mid = int(row["id"])
        for c in (row["cast"] or []):
            pid = c.get("id")
            if pid is None:
                continue
            key = (mid, int(pid))
            if key not in seen:
                seen.add(key)
                rows.append((mid, int(pid), _none(c.get("order"))))
    if not rows:
        return
    cur.executemany(
        "INSERT INTO cast_members (movie_id, person_id, cast_order) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
        rows,
    )
    log.debug("cast_members", extra={"n": len(rows)})


def _upsert_crew_members(cur, df: pd.DataFrame) -> None:
    rows, seen = [], set()
    for _, row in df.iterrows():
        mid = int(row["id"])
        for c in (row["crew"] or []):
            pid = c.get("id")
            job = c.get("job") or ""
            if pid is None or not job:
                continue
            key = (mid, int(pid), job)
            if key not in seen:
                seen.add(key)
                rows.append((mid, int(pid), job))
    if not rows:
        return
    cur.executemany(
        "INSERT INTO crew_members (movie_id, person_id, job) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
        rows,
    )
    log.debug("crew_members", extra={"n": len(rows)})


def _upsert_movie_keywords(cur, df: pd.DataFrame) -> None:
    rows, seen = [], set()
    for _, row in df.iterrows():
        mid = int(row["id"])
        for kw in (row["keywords"] or []):
            kid = kw.get("id")
            if kid is not None:
                key = (mid, int(kid))
                if key not in seen:
                    seen.add(key)
                    rows.append(key)
    if not rows:
        return
    cur.executemany(
        "INSERT INTO movie_keywords (movie_id, keyword_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        rows,
    )
    log.debug("movie_keywords", extra={"n": len(rows)})


def upsert_offline_columns(
    movie_ids: list[int],
    fused_embeddings: "np.ndarray",
    umap_coords: "np.ndarray",
) -> None:
    """Update movies with fused_embedding and UMAP coordinates from the offline pipeline.

    Args:
        movie_ids:        TMDB IDs in row order (must match array row order).
        fused_embeddings: Float32 array of shape (n, dim), L2-normalized.
        umap_coords:      Float64 array of shape (n, 2) with (x, y) columns.
    """
    url = get_env().database_url
    rows = [
        (fused_embeddings[i].tolist(), float(umap_coords[i, 0]), float(umap_coords[i, 1]), movie_ids[i])
        for i in range(len(movie_ids))
    ]
    with psycopg.connect(url) as conn:
        pgvector.psycopg.register_vector(conn)
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE movies SET fused_embedding = %s::vector, umap_x = %s, umap_y = %s WHERE id = %s",
                rows,
            )
    log.info("offline_columns_upserted", extra={"n": len(movie_ids)})


def ingest(
    df: pd.DataFrame,
    text_embeddings: np.ndarray,
    review_embeddings: np.ndarray | None = None,
    trailer_embeddings: np.ndarray | None = None,
) -> None:
    """Upsert all catalogue tables from *df* and pre-computed embeddings.

    Args:
        df:                 Cleaned DataFrame (output of clean.build_dataframe).
        text_embeddings:    Float32 array of shape (len(df), 1024), L2-normalized.
        review_embeddings:  Float32 array of shape (len(df), 1024), or None if
                            reviews are not yet available. Rows for movies without
                            reviews should be all-zero.
        trailer_embeddings: Float32 array of shape (len(df), 1024), or None if
                            trailer embeddings are not available. Rows for movies
                            without trailers should be all-zero.
    """
    if len(df) != len(text_embeddings):
        raise ValueError(f"df has {len(df)} rows but text_embeddings has {len(text_embeddings)} rows")
    if review_embeddings is not None and len(df) != len(review_embeddings):
        raise ValueError(f"df has {len(df)} rows but review_embeddings has {len(review_embeddings)} rows")
    if trailer_embeddings is not None and len(df) != len(trailer_embeddings):
        raise ValueError(f"df has {len(df)} rows but trailer_embeddings has {len(trailer_embeddings)} rows")

    url = get_env().database_url
    log.info("ingest_start", extra={"rows": len(df)})

    with psycopg.connect(url) as conn:
        pgvector.psycopg.register_vector(conn)
        with conn.cursor() as cur:
            _upsert_genres(cur, df)
            _upsert_people(cur, df)
            _upsert_keywords(cur, df)
            _upsert_movies(cur, df, text_embeddings, review_embeddings, trailer_embeddings)
            _upsert_movie_genres(cur, df)
            _upsert_cast_members(cur, df)
            _upsert_crew_members(cur, df)
            _upsert_movie_keywords(cur, df)

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("REINDEX TABLE movies")

    log.info("ingest_complete", extra={"movies": len(df)})
