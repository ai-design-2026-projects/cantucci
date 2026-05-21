"""In-memory domain types for clustering.

These are agent-facing types used for working state during the turn pipeline.
They are not DB rows: ``ClusterAssignment`` is a soft-membership score held
in memory, and ``ClusterSpecification`` is the write-input handed to the
session layer's ``snapshot_clusters``.
"""

import uuid
from dataclasses import dataclass


@dataclass
class ClusterAssignment:
    """Soft-cluster membership score for a single film."""

    movie_id: int
    score: float
    excluded: bool
    title: str | None = None


@dataclass
class ClusterSpecification:
    """Input spec for snapshot_clusters: one item per cluster to insert."""

    name: str
    description: str | None
    level: int
    centroid: list[float] | None
    parent_cluster_id: uuid.UUID | None
    assignments: list[tuple[int, float, bool]]


@dataclass
class ClusterPayload:
    """Pre-built per-cluster data passed to the describer LLM call."""

    cluster_index: int
    top_titles: list[str]
    top_genres: list[str]
    sample_overviews: list[str]
