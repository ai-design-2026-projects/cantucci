"""Regression tests for the catalogue ingest pipeline."""

from pathlib import Path

from db.ingestion import clean, split


def test_prepare_returns_unique_movie_ids():
    """The cleaned catalogue should contain exactly one row per movie id."""
    df = clean.prepare(Path("data/raw"))

    assert df["id"].is_unique
    assert df["id"].duplicated().sum() == 0


def test_three_way_keeps_artifacts_disjoint_by_id():
    """The three-way split should keep main, mini, and eval disjoint by id."""
    df = clean.prepare(Path("data/raw"))

    main_df, mini_df, eval_df = split.three_way(df, mini_size=50, eval_frac=0.05, seed=7)

    main_ids = set(main_df["id"])
    mini_ids = set(mini_df["id"])
    eval_ids = set(eval_df["id"])

    assert main_ids.isdisjoint(mini_ids)
    assert main_ids.isdisjoint(eval_ids)
    assert mini_ids.isdisjoint(eval_ids)