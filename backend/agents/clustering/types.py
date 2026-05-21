import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ClusterDraft:
    """A cluster to be written to the DB as part of a new cluster snapshot.

    Attributes:
        label:             Human-readable label.
        summary:           One-sentence description.
        exemplar_movie_ids: Top movie IDs by probability.
        parent_cluster_id: Source cluster UUID for drill-down operations.
        memberships:       List of (movie_id, probability) pairs.
    """
    label: str
    summary: str | None
    exemplar_movie_ids: list[int]
    parent_cluster_id: uuid.UUID | None
    memberships: list[tuple[int, float]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ClusterSnapshotDraft:
    """A complete cluster snapshot ready to be persisted.

    Attributes:
        operation: Operation name (e.g. ``"drill_down"``, ``"merge"``, ``"recut"``).
        params:    Replayability parameters dict.
        clusters:  List of cluster drafts.
    """
    operation: str
    params: dict
    clusters: list[ClusterDraft] = field(default_factory=list)
