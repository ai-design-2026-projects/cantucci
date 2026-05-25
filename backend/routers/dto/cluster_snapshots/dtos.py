import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ClusterDto(BaseModel):
    """A single cluster within a cluster snapshot.

    Attributes:
        id:                 Cluster UUID.
        label:              Human-readable label.
        summary:            One-sentence description.
        exemplar_movie_ids: Top movie IDs by probability.
        parent_cluster_id:  UUID of the source cluster, if this was a drill-down.
        size:               Total number of movies with non-zero membership.
    """
    id: uuid.UUID
    label: str | None
    summary: str | None
    exemplar_movie_ids: list[int]
    parent_cluster_id: uuid.UUID | None
    size: int


class ClusterSnapshotDto(BaseModel):
    """A cluster snapshot with its full cluster list.

    Attributes:
        id:          Cluster snapshot UUID.
        parent_id:   Parent cluster snapshot UUID, or None for the root.
        operation:   Operation that produced this snapshot.
        params:      Replayability parameters.
        config_hash: SHA-256 prefix of the YAML config that produced this snapshot.
        clusters:    All clusters in this snapshot.
        created_at:  UTC creation timestamp.
    """
    id: uuid.UUID
    parent_id: uuid.UUID | None
    operation: str
    params: dict[str, Any]
    config_hash: str
    clusters: list[ClusterDto]
    created_at: datetime


class ClusterSnapshotGraphDto(BaseModel):
    """The full cluster snapshot graph for a conversation (for future Obsidian-style viz).

    Attributes:
        cluster_snapshots: All cluster snapshot rows for the conversation (no cluster detail).
    """
    cluster_snapshots: list[dict[str, Any]]


class ClusterMembershipDto(BaseModel):
    """A single movie's membership in a cluster.

    Attributes:
        movie_id:    TMDB integer movie ID.
        probability: Soft membership probability in (0, 1].
    """
    movie_id: int
    probability: float
