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
    """
    Load, clean, and enrich the raw Kaggle CSVs; return one row per movie.
    Args:
        raw_dir: Directory containing movies_metadata.csv, credits.csv, keywords.csv.
    Returns:
        Cleaned DataFrame with composite_text column ready for embedding.
    """
    log.info("loading CSVs", extra={"raw_dir": str(raw_dir)})
    metadata_df = pd.read_csv(raw_dir / "movies_metadata.csv", low_memory=False)
    credits_df = pd.read_csv(raw_dir / "credits.csv")
    keywords_df = pd.read_csv(raw_dir / "keywords.csv")

    # Drop rows with missing or non-numeric ids, convert to int
    metadata_df = metadata_df[pd.to_numeric(metadata_df["id"], errors="coerce").notna()].copy()
    metadata_df["id"] = metadata_df["id"].astype(int)

    # Dedup by TMDB id (keep last)
    metadata_df = metadata_df.drop_duplicates(subset=["id"], keep="last")

    # Dedup by imdb_id for rows that have one (keep last)
    has_imdb = metadata_df["imdb_id"].notna() & (metadata_df["imdb_id"].astype(str).str.strip() != "")
    metadata_df = pd.concat([
        metadata_df[has_imdb].drop_duplicates(subset=["imdb_id"], keep="last"),
        metadata_df[~has_imdb],
    ])

    # Numeric coercions; 0 budget/revenue treated as missing (NaN)
    for col in ("budget", "revenue"):
        metadata_df[col] = pd.to_numeric(metadata_df[col], errors="coerce").replace(0.0, np.nan)
    for col in ("vote_average", "vote_count", "popularity", "runtime"):
        metadata_df[col] = pd.to_numeric(metadata_df[col], errors="coerce")

    # Booleans
    metadata_df["adult"] = metadata_df["adult"].apply(_parse_bool)
    metadata_df["video"] = metadata_df["video"].apply(_parse_bool)

    # Release date as "YYYY-MM-DD" string or None
    parsed_dates = pd.to_datetime(metadata_df["release_date"], errors="coerce")
    metadata_df["release_date"] = [d.strftime("%Y-%m-%d") if pd.notna(d) else None for d in parsed_dates]

    # Parse JSON-as-literal-string columns
    for col in ("genres", "production_companies", "production_countries", "spoken_languages"):
        metadata_df[col] = metadata_df[col].apply(_parse_list)
    metadata_df["belongs_to_collection"] = metadata_df["belongs_to_collection"].apply(_parse_dict)

    # Transform credits and keywords to have one row per movie id, with nested lists for cast/crew/keywords
    for df in (credits, keywords_df):
        df["id"] = pd.to_numeric(df["id"], errors="coerce")
    credits = credits.drop_duplicates(subset=["id"], keep="last")
    keywords_df = keywords_df.drop_duplicates(subset=["id"], keep="last")
    credits["cast"] = credits["cast"].apply(_parse_list)
    credits["crew"] = credits["crew"].apply(_parse_list)
    keywords_df["keywords"] = keywords_df["keywords"].apply(_parse_list)

    # Merge metadata with credits and keywords; fill missing nested fields with empty lists
    result_df = metadata_df.merge(credits, on="id", how="left").merge(keywords_df, on="id", how="left")
    result_df["cast"] = result_df["cast"].apply(lambda v: v if isinstance(v, list) else [])
    result_df["crew"] = result_df["crew"].apply(lambda v: v if isinstance(v, list) else [])
    result_df["keywords"] = result_df["keywords"].apply(lambda v: v if isinstance(v, list) else [])

    # Compute the derived fields: top3_cast, director, bayesian_rating, composite_text
    result_df["top3_cast"] = result_df["cast"].apply(_top3_cast)
    result_df["director"] = result_df["crew"].apply(_director)

    # Bayesian rating: (v*R + m*C) / (v+m), m=50, C = vote_count-weighted mean
    vc = result_df["vote_count"].fillna(0)
    va = result_df["vote_average"].fillna(0)
    C = float((va * vc).sum() / vc.sum()) if vc.sum() > 0 else 0.0
    m = 50
    result_df["bayesian_rating"] = (vc * va + m * C) / (vc + m)
    
    # Add composite_text column for embedding
    result_df["composite_text"] = result_df.apply(_composite_text, axis=1)

    # Post-condition guards
    assert len(result_df) >= 40_000, f"Expected ≥40k rows after cleaning, got {len(result_df)}"
    assert result_df["id"].isna().sum() == 0, "NaN ids remain after cleaning"
    assert result_df["id"].is_unique, "Duplicate ids remain after cleaning"
    assert (result_df["composite_text"].str.strip() == "").sum() == 0, "Empty composite_text rows"

    log.info("cleaning complete", extra={"rows": len(result_df)})
    return result_df.reset_index(drop=True)
