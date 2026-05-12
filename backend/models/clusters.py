"""Cluster-related types for the DB access layer."""

import uuid
from dataclasses import dataclass


@dataclass
class ClusterSpec:
    """Input spec for snapshot_clusters: one item per cluster to insert."""

    name: str
    description: str | None
    level: int
    centroid: list[float] | None
    parent_cluster_id: uuid.UUID | None
    # List of (movie_id, score, excluded) tuples
    assignments: list[tuple[int, float, bool]]


@dataclass
class ClusterAssignment:
    movie_id: int
    score: float
    excluded: bool


@dataclass
class ClusterSnapshot:
    id: uuid.UUID
    name: str
    description: str | None
    level: int
    parent_cluster_id: uuid.UUID | None
    assignments: list[ClusterAssignment]
