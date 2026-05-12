"""Catalogue DB ingest — idempotent upserts for all catalogue tables.

SQL lives here directly (offline exception analogous to db/apply.py).
Uses a single psycopg connection; all inserts run inside one transaction.
"""
import logging

import numpy as np
import pandas as pd
import psycopg
import pgvector.psycopg

import backend.config as config

log = logging.getLogger(__name__)


def _none(val):
    """Return None for NaN/NaT/None; pass everything else through."""
    try:
        return None if pd.isna(val) else val
    except (TypeError, ValueError):
        return val


def _upsert_collections(cur, df: pd.DataFrame) -> None:
    rows, seen = [], set()
    for coll in df["belongs_to_collection"]:
        if not isinstance(coll, dict):
            continue
        cid = coll.get("id")
        if cid is None or cid in seen:
            continue
        seen.add(cid)
        rows.append((int(cid), coll.get("name"), coll.get("poster_path"), coll.get("backdrop_path")))
    if not rows:
        return
    cur.executemany(
        "INSERT INTO collections (id, name, poster_path, backdrop_path) VALUES (%s,%s,%s,%s)"
        " ON CONFLICT (id) DO UPDATE SET"
        "  name=EXCLUDED.name, poster_path=EXCLUDED.poster_path, backdrop_path=EXCLUDED.backdrop_path",
        rows,
    )
    log.debug("collections", extra={"n": len(rows)})


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
    seen: dict[int, tuple[str, int]] = {}
    for col in ("cast", "crew"):
        for members in df[col]:
            for m in (members or []):
                pid = m.get("id")
                if pid is not None and pid not in seen:
                    seen[int(pid)] = (m.get("name", ""), int(m.get("gender") or 0))
    rows = [(pid, name, gender) for pid, (name, gender) in seen.items()]
    if not rows:
        return
    cur.executemany(
        "INSERT INTO people (id, name, gender) VALUES (%s,%s,%s)"
        " ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, gender=EXCLUDED.gender",
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


def _upsert_production_companies(cur, df: pd.DataFrame) -> None:
    seen: dict[int, str] = {}
    for companies in df["production_companies"]:
        for c in (companies or []):
            cid = c.get("id")
            if cid is not None and cid not in seen:
                seen[int(cid)] = c.get("name", "")
    rows = list(seen.items())
    if not rows:
        return
    cur.executemany(
        "INSERT INTO production_companies (id, name) VALUES (%s,%s)"
        " ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name",
        rows,
    )
    log.debug("production_companies", extra={"n": len(rows)})


def _upsert_languages(cur, df: pd.DataFrame) -> None:
    seen: dict[str, str] = {}
    for langs in df["spoken_languages"]:
        for lang in (langs or []):
            iso = lang.get("iso_639_1")
            if iso and iso not in seen:
                seen[iso] = lang.get("name", "")
    rows = list(seen.items())
    if not rows:
        return
    cur.executemany(
        "INSERT INTO languages (iso_639_1, name) VALUES (%s,%s)"
        " ON CONFLICT (iso_639_1) DO UPDATE SET name=EXCLUDED.name",
        rows,
    )
    log.debug("languages", extra={"n": len(rows)})


def _upsert_countries(cur, df: pd.DataFrame) -> None:
    seen: dict[str, str] = {}
    for countries in df["production_countries"]:
        for c in (countries or []):
            iso = c.get("iso_3166_1")
            if iso and iso not in seen:
                seen[iso] = c.get("name", "")
    rows = list(seen.items())
    if not rows:
        return
    cur.executemany(
        "INSERT INTO countries (iso_3166_1, name) VALUES (%s,%s)"
        " ON CONFLICT (iso_3166_1) DO UPDATE SET name=EXCLUDED.name",
        rows,
    )
    log.debug("countries", extra={"n": len(rows)})



def _upsert_movies(cur, df: pd.DataFrame, embeddings: np.ndarray) -> None:
    rows = []
    for i, (_, row) in enumerate(df.iterrows()):
        coll = row.get("belongs_to_collection")
        coll_id = int(coll["id"]) if isinstance(coll, dict) and coll.get("id") is not None else None
        rows.append((
            int(row["id"]),
            _none(row.get("imdb_id")),
            _none(row.get("title")),
            _none(row.get("original_title")),
            _none(row.get("original_language")),
            _none(row.get("overview")),
            _none(row.get("tagline")),
            _none(row.get("release_date")),                          # DATE string "YYYY-MM-DD"
            float(row["runtime"]) if pd.notna(row.get("runtime")) else None,
            int(row["budget"]) if pd.notna(row.get("budget")) else None,
            int(row["revenue"]) if pd.notna(row.get("revenue")) else None,
            float(row["popularity"]) if pd.notna(row.get("popularity")) else None,
            float(row["vote_average"]) if pd.notna(row.get("vote_average")) else None,
            int(row["vote_count"]) if pd.notna(row.get("vote_count")) else None,
            float(row["bayesian_rating"]) if pd.notna(row.get("bayesian_rating")) else None,
            _none(row.get("status")),
            bool(row.get("adult", False)),
            bool(row.get("video", False)),
            _none(row.get("poster_path")),
            _none(row.get("homepage")),
            coll_id,
            embeddings[i],
        ))
    cur.executemany(
        """
        INSERT INTO movies (
            id, imdb_id, title, original_title, original_language,
            overview, tagline, release_date, runtime,
            budget, revenue, popularity, vote_average, vote_count,
            bayesian_rating, status, adult, video, poster_path, homepage,
            collection_id, embedding
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        ON CONFLICT (id) DO UPDATE SET
            imdb_id=EXCLUDED.imdb_id, title=EXCLUDED.title,
            original_title=EXCLUDED.original_title,
            original_language=EXCLUDED.original_language,
            overview=EXCLUDED.overview, tagline=EXCLUDED.tagline,
            release_date=EXCLUDED.release_date, runtime=EXCLUDED.runtime,
            budget=EXCLUDED.budget, revenue=EXCLUDED.revenue,
            popularity=EXCLUDED.popularity, vote_average=EXCLUDED.vote_average,
            vote_count=EXCLUDED.vote_count, bayesian_rating=EXCLUDED.bayesian_rating,
            status=EXCLUDED.status, adult=EXCLUDED.adult, video=EXCLUDED.video,
            poster_path=EXCLUDED.poster_path, homepage=EXCLUDED.homepage,
            collection_id=EXCLUDED.collection_id, embedding=EXCLUDED.embedding
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
            cid = c.get("credit_id") or ""
            key = (mid, int(pid), cid)
            if key not in seen:
                seen.add(key)
                rows.append((mid, int(pid), _none(c.get("character")), _none(c.get("order")), cid))
    if not rows:
        return
    cur.executemany(
        "INSERT INTO cast_members (movie_id, person_id, character, cast_order, credit_id)"
        " VALUES (%s,%s,%s,%s,%s)"
        " ON CONFLICT (movie_id, person_id, credit_id)"
        " DO UPDATE SET character=EXCLUDED.character, cast_order=EXCLUDED.cast_order",
        rows,
    )
    log.debug("cast_members", extra={"n": len(rows)})


def _upsert_crew_members(cur, df: pd.DataFrame) -> None:
    rows, seen = [], set()
    for _, row in df.iterrows():
        mid = int(row["id"])
        for c in (row["crew"] or []):
            pid = c.get("id")
            if pid is None:
                continue
            cid = c.get("credit_id") or ""
            key = (mid, int(pid), cid)
            if key not in seen:
                seen.add(key)
                rows.append((mid, int(pid), _none(c.get("department")), _none(c.get("job")), cid))
    if not rows:
        return
    cur.executemany(
        "INSERT INTO crew_members (movie_id, person_id, department, job, credit_id)"
        " VALUES (%s,%s,%s,%s,%s)"
        " ON CONFLICT (movie_id, person_id, credit_id)"
        " DO UPDATE SET department=EXCLUDED.department, job=EXCLUDED.job",
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


def _upsert_movie_companies(cur, df: pd.DataFrame) -> None:
    rows, seen = [], set()
    for _, row in df.iterrows():
        mid = int(row["id"])
        for c in (row["production_companies"] or []):
            cid = c.get("id")
            if cid is not None:
                key = (mid, int(cid))
                if key not in seen:
                    seen.add(key)
                    rows.append(key)
    if not rows:
        return
    cur.executemany(
        "INSERT INTO movie_companies (movie_id, company_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        rows,
    )
    log.debug("movie_companies", extra={"n": len(rows)})


def _upsert_movie_spoken_languages(cur, df: pd.DataFrame) -> None:
    rows, seen = [], set()
    for _, row in df.iterrows():
        mid = int(row["id"])
        for lang in (row["spoken_languages"] or []):
            iso = lang.get("iso_639_1")
            if iso:
                key = (mid, iso)
                if key not in seen:
                    seen.add(key)
                    rows.append(key)
    if not rows:
        return
    cur.executemany(
        "INSERT INTO movie_spoken_languages (movie_id, iso_639_1) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        rows,
    )
    log.debug("movie_spoken_languages", extra={"n": len(rows)})


def _upsert_movie_countries(cur, df: pd.DataFrame) -> None:
    rows, seen = [], set()
    for _, row in df.iterrows():
        mid = int(row["id"])
        for c in (row["production_countries"] or []):
            iso = c.get("iso_3166_1")
            if iso:
                key = (mid, iso)
                if key not in seen:
                    seen.add(key)
                    rows.append(key)
    if not rows:
        return
    cur.executemany(
        "INSERT INTO movie_countries (movie_id, iso_3166_1) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        rows,
    )
    log.debug("movie_countries", extra={"n": len(rows)})



def ingest(df: pd.DataFrame, embeddings: np.ndarray) -> None:
    """Upsert all catalogue tables from *df* and pre-computed *embeddings*.

    Wraps the entire operation in a single transaction; rolls back on any error.

    Args:
        df: Cleaned DataFrame (output of clean.prepare or loaded from parquet artifact).
        embeddings: Float32 array of shape (len(df), 384) aligned with df rows.
    """
    if len(df) != len(embeddings):
        raise ValueError(f"df has {len(df)} rows but embeddings has {len(embeddings)} rows")

    url = config.database_url()
    log.info("connecting to DB for ingest", extra={"rows": len(df)})

    with psycopg.connect(url) as conn:
        pgvector.psycopg.register_vector(conn)
        with conn.cursor() as cur:
            # Lookup tables first (no FK deps on movies)
            _upsert_collections(cur, df)
            _upsert_genres(cur, df)
            _upsert_people(cur, df)
            _upsert_keywords(cur, df)
            _upsert_production_companies(cur, df)
            _upsert_languages(cur, df)
            _upsert_countries(cur, df)
            # Movies (FK → collections)
            _upsert_movies(cur, df, embeddings)
            # Join tables (FK → movies + lookup tables)
            _upsert_movie_genres(cur, df)
            _upsert_cast_members(cur, df)
            _upsert_crew_members(cur, df)
            _upsert_movie_keywords(cur, df)
            _upsert_movie_companies(cur, df)
            _upsert_movie_spoken_languages(cur, df)
            _upsert_movie_countries(cur, df)
        # conn.__exit__ commits on success, rolls back on exception

    log.info("ingest complete", extra={"movies": len(df)})
