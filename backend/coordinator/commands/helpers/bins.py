from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from backend.agents.intent.types import PartitionAttribute, PartitionBin
from backend.data_access.movies.types import NumericStats

log = logging.getLogger(__name__)

NUMERIC_ATTRIBUTES = {
    PartitionAttribute.RUNTIME,
    PartitionAttribute.RELEASE_YEAR,
    PartitionAttribute.VOTE_AVERAGE,
}


@dataclass(frozen=True, slots=True)
class _AttrSpec:
    """Per-attribute configuration for bin edge selection and label generation."""

    candidates: list[float]
    fmt: Callable[[float], str]
    all_label: str
    two: tuple[str, str]
    three: tuple[str, str, str]


_SPECS: dict[str, _AttrSpec] = {
    "runtime": _AttrSpec(
        candidates=[45.0, 60.0, 75.0, 90.0, 105.0, 120.0, 135.0, 150.0, 180.0, 210.0],
        fmt=lambda v: str(int(v)),
        all_label="All films",
        two=("Short (<{e} min)", "Long (≥{e} min)"),
        three=("Short (<{lo} min)", "Medium ({lo}–{hi} min)", "Long (≥{hi} min)"),
    ),
    "release_year": _AttrSpec(
        candidates=[1940.0, 1950.0, 1960.0, 1970.0, 1980.0, 1990.0, 2000.0, 2010.0, 2020.0],
        fmt=lambda v: str(int(v)),
        all_label="All films",
        two=("Before {e}", "{e}–present"),
        three=("Before {lo}", "{lo}–{hi}", "{hi}–present"),
    ),
    "vote_average": _AttrSpec(
        candidates=[4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5],
        fmt=lambda v: f"{v:.1f}",
        all_label="All films",
        two=("Below average (<{e})", "Above average (≥{e})"),
        three=("Low (<{lo})", "Average ({lo}–{hi})", "Acclaimed (≥{hi})"),
    ),
}


def _select_edges(stats: NumericStats, candidates: list[float]) -> list[float]:
    """Return up to 2 edges from candidates, snapped to the p25/p75 positions of the distribution.

    Only candidates strictly between the data min and max are considered, so edges
    always produce non-empty bins. Duplicate snapped values are dropped, which may
    yield 0 or 1 edge when the distribution is very narrow.
    """
    lo = stats.min_val if stats.min_val is not None else candidates[0]
    hi = stats.max_val if stats.max_val is not None else candidates[-1]
    valid = [c for c in candidates if lo < c < hi]
    if not valid:
        return []
    targets = [v for v in (stats.p25, stats.p75) if v is not None]
    if not targets:
        targets = [v for v in (stats.p50,) if v is not None]
    edges: list[float] = []
    for target in targets:
        nearest = min(valid, key=lambda c: abs(c - target))
        if nearest not in edges:
            edges.append(nearest)
    return sorted(edges)


def _build_bins(spec: _AttrSpec, edges: list[float]) -> list[PartitionBin]:
    """Build labelled PartitionBin objects from the selected edge values."""
    if not edges:
        return [PartitionBin(label=spec.all_label, min=None, max=None)]
    if len(edges) == 1:
        e = spec.fmt(edges[0])
        lo_label, hi_label = spec.two
        return [
            PartitionBin(label=lo_label.format(e=e), min=None, max=edges[0]),
            PartitionBin(label=hi_label.format(e=e), min=edges[0], max=None),
        ]
    lo_f, hi_f = spec.fmt(edges[0]), spec.fmt(edges[1])
    lo_label, mid_label, hi_label = spec.three
    return [
        PartitionBin(label=lo_label.format(lo=lo_f, hi=hi_f), min=None, max=edges[0]),
        PartitionBin(label=mid_label.format(lo=lo_f, hi=hi_f), min=edges[0], max=edges[1]),
        PartitionBin(label=hi_label.format(lo=lo_f, hi=hi_f), min=edges[1], max=None),
    ]


def propose_bins(attribute: str, stats: NumericStats) -> list[PartitionBin]:
    """Propose labelled bins for a numeric partition attribute using the data distribution.

    Bins are selected deterministically: for each attribute a fixed set of
    round-number candidate edges is defined; edges are chosen by snapping the p25
    and p75 positions of the actual distribution to the nearest candidate, then
    labelled with human-friendly strings.

    Args:
        attribute: Partition attribute name — one of ``"runtime"``,
                   ``"release_year"``, or ``"vote_average"``.
        stats:     Distribution statistics for the attribute within the in-scope
                   movie set.

    Returns:
        Ordered list of ``PartitionBin`` objects ready to pass to ``partition_by``
        after user confirmation.

    Raises:
        ValueError: If *attribute* is not a supported numeric attribute.
    """
    if attribute not in _SPECS:
        raise ValueError(
            f"Unsupported numeric attribute '{attribute}'. Valid: {sorted(_SPECS)}"
        )

    spec = _SPECS[attribute]
    edges = _select_edges(stats, spec.candidates)
    bins = _build_bins(spec, edges)

    log.info(
        "partition_advisor_proposed",
        extra={
            "attribute": attribute,
            "n_bins": len(bins),
            "bin_labels": [b.label for b in bins],
        },
    )
    return bins
