"""
Pure statistical helpers for eval metric aggregation.

No DB access, no imports outside the stdlib.  All functions are deterministic
when a seed is provided.
"""

import math
import random
from dataclasses import dataclass
from typing import Sequence


@dataclass
class MetricCI:
    """Point estimate plus 95% confidence interval bounds for a single metric.

    Attributes:
        value: Point estimate (mean or proportion).
        ci_lo: Lower bound of the 95% CI.
        ci_hi: Upper bound of the 95% CI.
        n:     Sample size used to compute the estimate.
    """

    value: float
    ci_lo: float
    ci_hi: float
    n: int


def bootstrap_ci(
    values: Sequence[float],
    n_iter: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> MetricCI:
    """Percentile bootstrap CI for the mean of ``values``.

    Resamples ``values`` with replacement ``n_iter`` times using a seeded
    RNG so results are reproducible across calls.

    Args:
        values: Observed metric values (must be non-empty for a finite result).
        n_iter: Number of bootstrap resamples.
        alpha:  Two-sided significance level (default 0.05 → 95% CI).
        seed:   RNG seed for reproducibility.

    Returns:
        MetricCI with value=mean, ci_lo=α/2 percentile, ci_hi=(1-α/2) percentile.
        Returns ``MetricCI(nan, nan, nan, 0)`` if ``values`` is empty.
    """
    n = len(values)
    if n == 0:
        nan = float("nan")
        return MetricCI(value=nan, ci_lo=nan, ci_hi=nan, n=0)

    rng = random.Random(seed)
    pop = list(values)
    means = sorted(
        sum(rng.choices(pop, k=n)) / n
        for _ in range(n_iter)
    )

    lo_idx = max(0, int(alpha / 2 * n_iter))
    hi_idx = min(n_iter - 1, int((1 - alpha / 2) * n_iter) - 1)
    mean = sum(pop) / n

    return MetricCI(value=mean, ci_lo=means[lo_idx], ci_hi=means[hi_idx], n=n)


def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> MetricCI:
    """Wilson score confidence interval for a proportion.

    Closed-form — no resampling needed.  z is fixed at 1.96 for alpha=0.05;
    other alpha values are not supported and will silently use the same z.

    Args:
        successes: Number of "success" observations.
        n:         Total number of observations.
        alpha:     Significance level (only 0.05 is validated; ignored otherwise).

    Returns:
        MetricCI with value=successes/n, bounds clamped to [0, 1].
        Returns ``MetricCI(nan, nan, nan, 0)`` if n == 0.
    """
    if n == 0:
        nan = float("nan")
        return MetricCI(value=nan, ci_lo=nan, ci_hi=nan, n=0)

    z = 1.96
    p = successes / n
    z2 = z * z
    center = (p + z2 / (2 * n)) / (1 + z2 / n)
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)

    return MetricCI(
        value=p,
        ci_lo=max(0.0, center - margin),
        ci_hi=min(1.0, center + margin),
        n=n,
    )
