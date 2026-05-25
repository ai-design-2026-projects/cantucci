import uuid
from dataclasses import dataclass, field
from enum import Enum


class NavigationMode(str, Enum):
    """The type of clustering operation the user is requesting.

    Attributes:
        DRILL_DOWN:    Split one cluster further along a semantic dimension.
        MERGE:         Combine two or more clusters into one.
        RECUT:         Re-cluster the full dataset (or a filtered subset) from scratch.
        ANCHOR_SEARCH: Find movies similar to exemplars named by the user.
        CROSS_FILTER:  Apply a metadata filter (genre, year, etc.) to the current cluster snapshot.
        RESET:         Return to the root base cluster snapshot.
        EXPLAIN:       Explain why a movie belongs (or doesn't belong) in a cluster.
        SMALL_TALK:    Casual, non-operational message — answer directly without clustering.
    """
    DRILL_DOWN = "drill_down"
    MERGE = "merge"
    RECUT = "recut"
    ANCHOR_SEARCH = "anchor_search"
    CROSS_FILTER = "cross_filter"
    RESET = "reset"
    EXPLAIN = "explain"
    SMALL_TALK = "small_talk"


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
