"""Load and preprocess the raw Kaggle CSVs into a single clean DataFrame."""
import ast
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def _parse_list(val) -> list:
    """Parse a Python-literal string to a list; return [] on failure."""
    if pd.isna(val) or not isinstance(val, str) or not val.strip():
        return []
    try:
        result = ast.literal_eval(val)
        return result if isinstance(result, list) else []
    except (ValueError, SyntaxError):
        return []


def _parse_dict(val) -> dict | None:
    """Parse a Python-literal string to a dict; return None on failure."""
    if pd.isna(val) or not isinstance(val, str) or not val.strip():
        return None
    try:
        result = ast.literal_eval(val)
        return result if isinstance(result, dict) else None
    except (ValueError, SyntaxError):
        return None


def _parse_bool(val) -> bool:
    """Parse a value to boolean; treat NaN as False, strings "true"/"false" (case-insensitive), and pass through actual booleans."""
    if pd.isna(val):
        return False
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() == "true"


def _top3_cast(cast_list: list) -> list[str]:
    """Extract the top 3 cast member names based on "order" field; return empty list if not present."""
    sorted_cast = sorted(cast_list, key=lambda c: c.get("order", 999))
    return [c["name"] for c in sorted_cast[:3] if "name" in c]


def _director(crew_list: list) -> str:
    """Extract the director's name from the crew list; return empty string if not found."""
    for c in crew_list:
        if c.get("job") == "Director" and "name" in c:
            return c["name"]
    return ""


def _composite_text(row: pd.Series) -> str:
    """
    Combine multiple text fields into one for embedding.
    Fields used: title, original_title, overview, tagline, genres (names), 
    top3_cast, director.
    """
    genres_str = " ".join(g.get("name", "") for g in (row["genres"] or []))
    cast_str = " ".join(row["top3_cast"])
    parts = [
        row.get("title") or "",
        row.get("original_title") or "",
        row.get("overview") or "",
        row.get("tagline") or "",
        genres_str,
        cast_str,
        row["director"],
    ]
    parts_str = [str(p).strip() for p in parts if not pd.isna(p)]
    return " ".join(p for p in parts_str if p)


def prepare(raw_dir: Path) -> pd.DataFrame:
    """Load, clean, and enrich the raw Kaggle CSVs; return one row per movie.
    Args:
        raw_dir: Directory containing movies_metadata.csv, credits.csv, keywords.csv.
    Returns:
        Cleaned DataFrame with composite_text column ready for embedding.
    """
    log.info("loading CSVs", extra={"raw_dir": str(raw_dir)})
    meta = pd.read_csv(raw_dir / "movies_metadata.csv", low_memory=False)
    credits = pd.read_csv(raw_dir / "credits.csv")
    kw_df = pd.read_csv(raw_dir / "keywords.csv")

    # Drop 3 known-corrupt rows with non-numeric id
    meta = meta[pd.to_numeric(meta["id"], errors="coerce").notna()].copy()
    meta["id"] = meta["id"].astype(int)

    # Dedup by TMDB id (keep last)
    meta = meta.drop_duplicates(subset=["id"], keep="last")

    # Dedup by imdb_id for rows that have one (keep last)
    has_imdb = meta["imdb_id"].notna() & (meta["imdb_id"].astype(str).str.strip() != "")
    meta = pd.concat([
        meta[has_imdb].drop_duplicates(subset=["imdb_id"], keep="last"),
        meta[~has_imdb],
    ])

    # Numeric coercions; 0 budget/revenue treated as missing
    for col in ("budget", "revenue"):
        meta[col] = pd.to_numeric(meta[col], errors="coerce").replace(0.0, np.nan)
    for col in ("vote_average", "vote_count", "popularity", "runtime"):
        meta[col] = pd.to_numeric(meta[col], errors="coerce")

    # Booleans
    meta["adult"] = meta["adult"].apply(_parse_bool)
    meta["video"] = meta["video"].apply(_parse_bool)

    # Release date as "YYYY-MM-DD" string or None
    parsed_dates = pd.to_datetime(meta["release_date"], errors="coerce")
    meta["release_date"] = [d.strftime("%Y-%m-%d") if pd.notna(d) else None for d in parsed_dates]

    # Parse JSON-as-literal-string columns
    for col in ("genres", "production_companies", "production_countries", "spoken_languages"):
        meta[col] = meta[col].apply(_parse_list)
    meta["belongs_to_collection"] = meta["belongs_to_collection"].apply(_parse_dict)

    # Merge credits and keywords
    for df in (credits, kw_df):
        df["id"] = pd.to_numeric(df["id"], errors="coerce")
    credits = credits.drop_duplicates(subset=["id"], keep="last")
    kw_df = kw_df.drop_duplicates(subset=["id"], keep="last")
    credits["cast"] = credits["cast"].apply(_parse_list)
    credits["crew"] = credits["crew"].apply(_parse_list)
    kw_df["keywords"] = kw_df["keywords"].apply(_parse_list)

    result = meta.merge(credits, on="id", how="left").merge(kw_df, on="id", how="left")
    result["cast"] = result["cast"].apply(lambda v: v if isinstance(v, list) else [])
    result["crew"] = result["crew"].apply(lambda v: v if isinstance(v, list) else [])
    result["keywords"] = result["keywords"].apply(lambda v: v if isinstance(v, list) else [])

    # Derived columns
    result["top3_cast"] = result["cast"].apply(_top3_cast)
    result["director"] = result["crew"].apply(_director)

    # Bayesian rating: (v*R + m*C) / (v+m), m=50, C = vote_count-weighted mean
    vc = result["vote_count"].fillna(0)
    va = result["vote_average"].fillna(0)
    C = float((va * vc).sum() / vc.sum()) if vc.sum() > 0 else 0.0
    m = 50
    result["bayesian_rating"] = (vc * va + m * C) / (vc + m)

    result["composite_text"] = result.apply(_composite_text, axis=1)
    result = result.drop_duplicates(subset=["id"], keep="last")

    # Post-condition guards
    assert len(result) >= 40_000, f"Expected ≥40k rows after cleaning, got {len(result)}"
    assert result["id"].isna().sum() == 0, "NaN ids remain after cleaning"
    assert result["id"].is_unique, "Duplicate ids remain after cleaning"
    assert (result["composite_text"].str.strip() == "").sum() == 0, "Empty composite_text rows"

    log.info("cleaning complete", extra={"rows": len(result)})
    return result.reset_index(drop=True)
