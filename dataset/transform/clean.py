import logging
from typing import Any
import pandas as pd

log = logging.getLogger(__name__)

_BAYESIAN_PRIOR_VOTES = 50


def _top3_cast(cast_list: list[dict[str, Any]]) -> list[str]:
    """Top 3 cast names by billing order."""
    sorted_cast = sorted(cast_list, key=lambda c: c.get("order", 999))
    return [c["name"] for c in sorted_cast[:3] if "name" in c]


def _director(crew_list: list[dict[str, Any]]) -> str:
    """First crew member with job == Director, else ''."""
    for c in crew_list:
        if c.get("job") == "Director" and "name" in c:
            return c["name"]
    return ""


def _composite_text(row: dict[str, Any]) -> str:
    """Concatenate the high-signal text fields used for embedding.

    Title, original_title (if different), release year, genres, tagline,
    overview, top-3 cast, director, and keyword names.
    """
    def _s(v: Any) -> str:
        # NaN / None / numbers → ""; only real strings get stripped.
        # Pandas widens missing-string columns to float NaN, and `NaN or ""`
        # evaluates to NaN (NaN is truthy), so a naive `(row.get(k) or "").strip()`
        # crashes on the first missing tagline / overview.
        return v.strip() if isinstance(v, str) else ""

    def _l(v: Any) -> list:
        # Same trap as _s for list-typed columns: `NaN or []` evaluates to NaN,
        # then iteration explodes. Currently safe because map_record always
        # writes lists, but cheaper to guard than to debug 70k rows in.
        return v if isinstance(v, list) else []

    parts: list[str] = []
    title = _s(row.get("title"))
    original_title = _s(row.get("original_title"))
    parts.append(title)
    if original_title and original_title.lower() != title.lower():
        parts.append(original_title)

    year = row.get("release_year")
    # pd.notna handles None and float('nan'); `and year` keeps the original
    # truthy guard so 0 (or future negatives) don't end up in the text.
    if pd.notna(year) and year:
        parts.append(str(int(year)))

    parts.append(" ".join(g.get("name", "") for g in _l(row.get("genres"))))
    parts.append(_s(row.get("tagline")))
    parts.append(_s(row.get("overview")))
    parts.append(" ".join(_l(row.get("top3_cast"))))
    parts.append(_s(row.get("director")))
    parts.append(" ".join(k.get("name", "") for k in _l(row.get("keywords"))))

    return " ".join(p for p in (str(p).strip() for p in parts) if p)


def _trailer_youtube_key(rec: dict[str, Any]) -> str | None:
    """Extract the first official YouTube trailer key from a TMDB video response.

    Prefers entries where ``official == True``, then falls back to the first
    YouTube trailer regardless of official status. Returns None when no
    suitable trailer is found or the ``videos`` key is absent.

    Args:
        rec: Raw TMDB movie JSON dict, expected to include a ``videos`` key
             when ``append_to_response=videos`` was requested.

    Returns:
        YouTube video key string (the ``?v=`` part of a watch URL), or None.
    """
    results: list[dict[str, Any]] = ((rec.get("videos") or {}).get("results") or [])
    yt_trailers = [
        r for r in results
        if r.get("site") == "YouTube" and r.get("type") == "Trailer"
    ]
    if not yt_trailers:
        return None
    official = [r for r in yt_trailers if r.get("official")]
    chosen = (official or yt_trailers)[0]
    return chosen.get("key") or None


def map_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Map a raw TMDB JSON response into the cleaned-shape row dict.

    Output keys match what ``db/load.py`` and ``dataset/split.three_way``
    consume.
    """
    cast = list((rec.get("credits") or {}).get("cast") or [])
    crew = list((rec.get("credits") or {}).get("crew") or [])
    keywords = list((rec.get("keywords") or {}).get("keywords") or [])

    release_date = rec.get("release_date") or None
    if release_date == "":
        release_date = None
    release_year: int | None = None
    if release_date:
        try:
            release_year = int(release_date[:4])
        except ValueError:
            release_year = None

    budget = rec.get("budget")
    revenue = rec.get("revenue")
    row: dict[str, Any] = {
        "id": int(rec["id"]),
        "imdb_id": rec.get("imdb_id") or None,
        "title": rec.get("title") or rec.get("original_title") or "",
        "original_title": rec.get("original_title") or "",
        "original_language": rec.get("original_language") or None,
        "overview": rec.get("overview") or None,
        "tagline": rec.get("tagline") or None,
        "release_date": release_date,
        "release_year": release_year,
        "runtime": rec.get("runtime"),
        # Zero budget/revenue are the TMDB convention for "missing" — drop to NaN
        # so the bayesian_rating + downstream stats don't get poisoned.
        "budget": (budget if budget else None),
        "revenue": (revenue if revenue else None),
        "popularity": rec.get("popularity"),
        "vote_average": rec.get("vote_average"),
        "vote_count": rec.get("vote_count"),
        "status": rec.get("status") or None,
        "adult": bool(rec.get("adult", False)),
        "video": bool(rec.get("video", False)),
        "poster_path": rec.get("poster_path") or None,
        "homepage": rec.get("homepage") or None,
        "belongs_to_collection": rec.get("belongs_to_collection") or None,
        "genres": rec.get("genres") or [],
        "production_companies": rec.get("production_companies") or [],
        "production_countries": rec.get("production_countries") or [],
        "spoken_languages": rec.get("spoken_languages") or [],
        "cast": cast,
        "crew": crew,
        "keywords": keywords,
    }
    row["top3_cast"] = _top3_cast(cast)
    row["director"] = _director(crew)
    row["trailer_youtube_key"] = _trailer_youtube_key(rec)
    return row


def build_dataframe(
    records: list[dict[str, Any]],
    reviews: dict[int, str] | None = None,
) -> pd.DataFrame:
    """Map raw TMDB JSONs → cleaned DataFrame with composite_text + bayesian_rating.

    Args:
        records: Raw TMDB movie JSON dicts from ``tmdb_fetch``.
        reviews: Optional mapping of ``{movie_id: reviews_text}`` from
                 ``tmdb_fetch.fetch_all_reviews``.  Movies absent from the
                 mapping get a ``None`` (stored as NULL in the DB).

    Returns:
        Cleaned DataFrame with all columns expected by
        ``db/load.ingest``.
    """
    rows = [map_record(r) for r in records]
    df = pd.DataFrame(rows)

    df["vote_count"] = pd.to_numeric(df["vote_count"], errors="coerce")
    df["vote_average"] = pd.to_numeric(df["vote_average"], errors="coerce")
    vc = df["vote_count"].fillna(0)
    va = df["vote_average"].fillna(0)
    # Vote-count-weighted mean as the Bayesian prior, matching the legacy formula.
    prior_mean = float((va * vc).sum() / vc.sum()) if vc.sum() > 0 else 0.0
    m = _BAYESIAN_PRIOR_VOTES
    df["bayesian_rating"] = (vc * va + m * prior_mean) / (vc + m)

    df["composite_text"] = df.apply(_composite_text, axis=1)
    df["reviews_text"] = df["id"].map(reviews) if reviews else None

    assert df["id"].isna().sum() == 0, "NaN ids in snapshot"
    assert df["id"].is_unique, "Duplicate ids in snapshot"
    assert (df["composite_text"].str.strip() == "").sum() == 0, "Empty composite_text in snapshot"
    return df.reset_index(drop=True)
