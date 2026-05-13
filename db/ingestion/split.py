"""Deterministic three-way dataset split: main / mini / eval_holdout."""
import logging

import pandas as pd

log = logging.getLogger(__name__)


def three_way(
    df: pd.DataFrame,
    *,
    mini_size: int = 200,
    eval_frac: float = 0.10,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split df into (main, mini, eval_holdout).

    Eval holdout is a random slice taken first and is disjoint from everything
    else. Main is all remaining rows. Mini is the top-ranked subset of main by
    popularity (vote_count desc, popularity desc) — it is a strict subset of
    main, not a separate partition. Ingesting main always includes the mini movies.

    Args:
        df: Cleaned DataFrame from clean.prepare().
        mini_size: Number of rows in the mini set.
        eval_frac: Fraction of the full dataset reserved for evaluation.
        seed: Random state for reproducibility.

    Returns:
        Tuple of (main_df, mini_df, eval_df). mini_df IDs are a subset of main_df IDs.
    """
    eval_df = df.sample(frac=eval_frac, random_state=seed)
    main_df = df.drop(index=eval_df.index)

    ranked = main_df.sort_values(["vote_count", "popularity"], ascending=False)
    mini_df = ranked.head(mini_size)

    assert len(main_df) + len(eval_df) == len(df), "Split sizes do not sum"
    assert set(main_df["id"]).isdisjoint(eval_df["id"]), "main/eval overlap"
    assert set(mini_df["id"]).issubset(set(main_df["id"])), "mini not a subset of main"

    log.info(
        "split complete",
        extra={"main": len(main_df), "mini": len(mini_df), "eval_holdout": len(eval_df)},
    )
    return main_df.reset_index(drop=True), mini_df.reset_index(drop=True), eval_df.reset_index(drop=True)
