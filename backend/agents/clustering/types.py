import uuid
from dataclasses import dataclass, field
from enum import Enum

from backend.agents.concept.types import ConceptRep


class Modality(str, Enum):
    """
    Embedding spaces available for runtime distance computation.
    Values correspond to keys in ``fusion.runtime_weights`` config and to the
    embedding columns stored for each movie.

    Attributes:
        TEXT:    Fused text + review BGE embedding (always available).
        TRAILER: Trailer frame CLIP embedding (available when trailers were fetched).
        REVIEW:  Review-only BGE embedding.
    """
    TEXT = "text"
    TRAILER = "trailer"
    REVIEW = "review"

from enum import Enum


class NavigationMode(str, Enum):
    """Clustering operations a user can request.

    Dialogue-only intents (reset, explain, small_talk, go_to_base) live in
    ``intent.types.DialogueMode``.

    Attributes:
        DRILL_DOWN:   Split one cluster further along a semantic dimension, or cluster
                      the full catalogue when no source cluster is specified.
        MERGE:        Combine two or more clusters into one.
        FOCUS:        Keep only the selected cluster's members; discard all others.
        CROSS_FILTER: Keep only movies matching a metadata predicate, then re-cluster.
    """

    def __new__(cls, value: str, description: str = "") -> "NavigationMode":
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj._description = description
        return obj

    DRILL_DOWN = (
        "drill_down",
        "split one existing cluster further along a semantic concept, or re-cluster the full catalogue when no target cluster is specified",
    )
    MERGE = (
        "merge",
        "combine two or more clusters into one",
    )
    FOCUS = (
        "focus",
        "discard all clusters except the selected one, narrowing the working set to its members",
    )
    CROSS_FILTER = (
        "cross_filter",
        "keep only movies matching a metadata predicate (genre, year, director) "
        "then re-cluster the survivors",
    )

    @property
    def description(self) -> str:
        """One-line description of this mode for use in the intent prompt."""
        return self._description  # type: ignore[attr-defined]
    

@dataclass(frozen=True, slots=True)
class MetadataFilter:
    """Metadata predicate for the CROSS_FILTER operation.

    All populated fields are combined with AND logic; values within ``genres``
    are combined with OR.

    Attributes:
        genres:           Genre names to keep (OR across genres).
        release_year_min: Earliest release year, inclusive.
        release_year_max: Latest release year, inclusive.
        director:         Director name to match (case-insensitive substring).
    """
    genres: list[str] | None = None
    release_year_min: int | None = None
    release_year_max: int | None = None
    director: str | None = None


@dataclass(frozen=True, slots=True)
class NavigationRequest:
    """All inputs needed to dispatch a single clustering operation.

    Attributes:
        mode:                       Which clustering operation to run.
        parent_cluster_snapshot_id: The current (pre-operation) snapshot; ``None`` when
                                    the conversation is in the unclustered state.
        conversation_id:            Conversation to update after persisting.
        accumulated_cost:           Running LLM cost for the labelling budget.
        concept:                    Optional semantic concept (drill_down).
        source_cluster_id:          Cluster to split (drill_down) or focus on (focus).
                                    ``None`` for drill_down means cluster the full catalogue.
        cluster_ids:                Clusters to merge (merge).
        merged_label:               Label for the merged cluster.
        metadata_filter:            Metadata predicate for filtering (cross_filter).
        embedding_spaces:           Embedding modalities to fuse.
    """
    mode: NavigationMode
    parent_cluster_snapshot_id: uuid.UUID | None
    conversation_id: uuid.UUID
    accumulated_cost: float
    concept: ConceptRep | None = None
    source_cluster_id: uuid.UUID | None = None
    cluster_ids: list[uuid.UUID] | None = None
    merged_label: str | None = None
    metadata_filter: MetadataFilter | None = None
    embedding_spaces: list[Modality] | None = None


@dataclass(frozen=True, slots=True)
class ClusterDraft:
    """A cluster to be written to the DB as part of a new cluster snapshot.

    Attributes:
        label:              Human-readable label.
        summary:            One-sentence description.
        exemplar_movie_ids: Top movie IDs by probability.
        parent_cluster_id:  Source cluster UUID for drill-down operations.
        memberships:        List of (movie_id, probability) pairs.
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
        operation: Operation name (e.g. ``"drill_down"``, ``"merge"``, ``"cross_filter"``).
        params:    Replayability parameters dict.
        clusters:  List of cluster drafts.
    """
    operation: str
    params: dict
    clusters: list[ClusterDraft] = field(default_factory=list)

    def with_operation(self, operation: str, extra_params: dict | None = None) -> "ClusterSnapshotDraft":
        """Return a copy with a different operation name and optional extra params merged in.

        Used by cross_filter to stamp its own operation name over the drill_down base draft.

        Args:
            operation:   New operation string.
            extra_params: Additional key/value pairs to merge into params.
        """
        params = {**self.params, "operation": operation, **(extra_params or {})}
        return ClusterSnapshotDraft(operation=operation, params=params, clusters=self.clusters)
