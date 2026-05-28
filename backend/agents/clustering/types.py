import uuid
from dataclasses import dataclass, field
from enum import Enum


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


class NavigationMode(str, Enum):
    """Clustering operations a user can request via natural language."""
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
        "combine the two most-related clusters in the current view into one",
    )
    FOCUS = (
        "focus",
        "discard all clusters except the selected one, narrowing the working set to its members",
    )
    CROSS_FILTER = (
        "cross_filter",
        "keep only movies matching a metadata predicate (genre, year, director); "
        "no clustering is performed — use drill_down afterwards to cluster the filtered set",
    )
    PARTITION_BY = (
        "partition_by",
        "split the working set into deterministic clusters by an exact metadata "
        "attribute — genre, runtime, release year, or director",
    )
    EXCLUDE = (
        "exclude",
        "discard one selected cluster, keeping all other clusters in the working set (inverse of focus)",
    )

    @property
    def description(self) -> str:
        """One-line description of this mode for use in the intent prompt."""
        return self._description  # type: ignore[attr-defined]
    

class PartitionAttribute(str, Enum):
    """Metadata attributes supported by the ``partition_by`` operation.

    Attributes:
        GENRE:             Group by movie genre (multi-valued; a movie may appear in
                           multiple clusters).
        RUNTIME:           Bucket by runtime in minutes using LLM-specified numeric bins.
        RELEASE_YEAR:      Bucket by release year using LLM-specified numeric bins.
        DIRECTOR:          Group by director name (multi-valued when a movie has co-directors).
        VOTE_AVERAGE:      Bucket by audience rating (0–10 scale) using LLM-specified bins.
        ORIGINAL_LANGUAGE: Group by original production language (categorical).
    """
    GENRE = "genre"
    RUNTIME = "runtime"
    RELEASE_YEAR = "release_year"
    DIRECTOR = "director"
    VOTE_AVERAGE = "vote_average"
    ORIGINAL_LANGUAGE = "original_language"


@dataclass(frozen=True, slots=True)
class PartitionBin:
    """A single labelled bucket for numeric ``partition_by`` operations.

    ``min`` and ``max`` are both inclusive-lower / exclusive-upper edges.
    Either may be ``None`` to represent an open-ended range.

    Attributes:
        label: Human-readable bucket name (e.g. ``"Short (<1h)"``).
        min:   Lower bound in attribute units, inclusive; ``None`` = no lower bound.
        max:   Upper bound in attribute units, exclusive; ``None`` = no upper bound.
    """

    label: str
    min: float | None
    max: float | None


@dataclass(frozen=True, slots=True)
class PartitionSpec:
    """Full specification for a ``partition_by`` operation.

    Attributes:
        attribute: Which metadata field to group by.
        bins:      Required for numeric attributes (``RUNTIME``, ``RELEASE_YEAR``);
                   ``None`` for categorical attributes (``GENRE``, ``DIRECTOR``).
    """

    attribute: PartitionAttribute
    bins: list[PartitionBin] | None


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
class ClusterDraft:
    """A cluster to be written to the DB as part of a new cluster snapshot.

    Attributes:
        label:              Human-readable label, or None when the LLM labeler will generate it.
        summary:            One-sentence description, or None to trigger LLM labeling.
        exemplar_movie_ids: Top movie IDs by probability.
        parent_cluster_id:  Source cluster UUID for drill-down operations.
        memberships:        List of (movie_id, probability) pairs.
    """
    label: str | None
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

