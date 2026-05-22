import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ClusterSnapshotRow:
    """A row from the cluster_snapshots table.

    Snapshots are conversation-agnostic; the join table
    ``conversation_snapshot_refs`` records which conversations have touched
    a given snapshot.

    Attributes:
        id:          Cluster snapshot UUID.
        parent_id:   Parent cluster snapshot UUID, or None for the root.
        operation:   Operation that produced this snapshot (e.g. ``"base"``, ``"drill_down"``).
        params:      JSONB dict capturing algorithm + inputs for replayability.
        config_hash: SHA-256 prefix of the YAML config active when this snapshot
                     was produced (matches ``backend.settings.get_config_hash``).
        created_at:  UTC creation timestamp.
    """
    id: uuid.UUID
    parent_id: uuid.UUID | None
    operation: str
    params: dict[str, Any]
    config_hash: str
    created_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "ClusterSnapshotRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            parent_id=r["parent_id"],
            operation=r["operation"],
            params=r["params"],
            config_hash=r["config_hash"],
            created_at=r["created_at"],
        )


@dataclass(frozen=True, slots=True)
class ClusterRow:
    """A row from the clusters table.

    Attributes:
        id:                 Cluster UUID.
        cluster_snapshot_id: Parent cluster snapshot UUID.
        label:              Human-readable cluster label, or None for unlabeled root clusters.
        summary:            One-sentence LLM-generated summary.
        exemplar_movie_ids: Top-N movie IDs with highest membership probability.
        parent_cluster_id:  UUID of the cluster this was split from, if any.
    """
    id: uuid.UUID
    cluster_snapshot_id: uuid.UUID
    label: str | None
    summary: str | None
    exemplar_movie_ids: list[int]
    parent_cluster_id: uuid.UUID | None

    @classmethod
    def from_row(cls, r: dict) -> "ClusterRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            cluster_snapshot_id=r["cluster_snapshot_id"],
            label=r["label"],
            summary=r["summary"],
            exemplar_movie_ids=list(r["exemplar_movie_ids"]) if r["exemplar_movie_ids"] else [],
            parent_cluster_id=r["parent_cluster_id"],
        )


@dataclass(frozen=True, slots=True)
class ClusterMembershipRow:
    """A row from the cluster_memberships table.

    Attributes:
        cluster_id:  Cluster UUID.
        movie_id:    TMDB integer ID.
        probability: Soft membership probability in (0, 1].
    """
    cluster_id: uuid.UUID
    movie_id: int
    probability: float

    @classmethod
    def from_row(cls, r: dict) -> "ClusterMembershipRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            cluster_id=r["cluster_id"],
            movie_id=r["movie_id"],
            probability=r["probability"],
        )


@dataclass(frozen=True, slots=True)
class ClusterSnapshotWithClusters:
    """A cluster snapshot combined with its cluster list (no membership rows).

    Attributes:
        cluster_snapshot: The cluster snapshot row.
        clusters:         All clusters belonging to this snapshot.
    """
    cluster_snapshot: ClusterSnapshotRow
    clusters: list[ClusterRow] = field(default_factory=list)
