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
    """Split df into (main, mini, eval_holdout). All three are disjoint by id.

    Eval holdout is a random slice taken first. Mini is drawn from the remaining
    rows ranked by popularity (vote_count desc, popularity desc) so it contains
    well-known titles suitable for dev/CI use. Main is everything else.

    Args:
        df: Cleaned DataFrame from clean.prepare().
        mini_size: Number of rows in the mini set.
        eval_frac: Fraction of the full dataset reserved for evaluation.
        seed: Random state for reproducibility.

    Returns:
        Tuple of (main_df, mini_df, eval_df).
    """
    eval_df = df.sample(frac=eval_frac, random_state=seed)
    remainder = df.drop(index=eval_df.index)

    # Mini: top-ranked by popularity so it's useful as demo data
    ranked = remainder.sort_values(["vote_count", "popularity"], ascending=False)
    mini_df = ranked.head(mini_size)
    main_df = remainder.drop(index=mini_df.index)

    assert len(main_df) + len(mini_df) + len(eval_df) == len(df), "Split sizes do not sum"
    assert set(main_df["id"]).isdisjoint(eval_df["id"]), "main/eval overlap"
    assert set(mini_df["id"]).isdisjoint(eval_df["id"]), "mini/eval overlap"

    log.info(
        "split complete",
        extra={"main": len(main_df), "mini": len(mini_df), "eval_holdout": len(eval_df)},
    )
    return main_df.reset_index(drop=True), mini_df.reset_index(drop=True), eval_df.reset_index(drop=True)
