import logging
import pandas as pd

log = logging.getLogger(__name__)


def three_way(
    df: pd.DataFrame,
    *,
    mini_size: int,
    eval_frac: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split df into (main, mini, eval_holdout).
    - Eval holdout is a random slice taken first and is disjoint from everything
    else. This allow us to make unbiased evaluation measurements on the system.
    - Main is all remaining rows, the production set for the system. 
    - Mini is the top-ranked subset of main by popularity (vote_count desc, popularity desc).
    It is a strict subset of main, not a separate partition. 
    
    Args:
        - df: Cleaned DataFrame from clean.prepare().
        - mini_size: Number of rows in the mini set.
        - eval_frac: Fraction of the full dataset reserved for evaluation.
        - seed: Random state for reproducibility.

    Returns:
        - Tuple of (main_df, mini_df, eval_df). mini_df IDs are a subset of main_df IDs.
    """
    # Extract eval holdout first to ensure it's a random slice disjoint from main/mini
    eval_df = df.sample(frac=eval_frac, random_state=seed)
    main_df = df.drop(index=eval_df.index)
    
    # Rank main by popularity
    ranked = main_df.sort_values(["vote_count", "popularity"], ascending=False)
    # Extract top mini_size rows for the mini set; these are a subset of main_df
    mini_df = ranked.head(mini_size)

    # Assertions to verify the splits are correct
    assert len(main_df) + len(eval_df) == len(df), "Split sizes do not sum"
    assert set(main_df["id"]).isdisjoint(eval_df["id"]), "main/eval overlap"
    assert set(mini_df["id"]).issubset(set(main_df["id"])), "mini not a subset of main"

    log.info(
        "split complete",
        extra={"main": len(main_df), "mini": len(mini_df), "eval_holdout": len(eval_df)},
    )
    return main_df.reset_index(drop=True), mini_df.reset_index(drop=True), eval_df.reset_index(drop=True)
