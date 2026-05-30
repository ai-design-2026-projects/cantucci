import logging
import uuid
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel

log = logging.getLogger(__name__)


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

    CLUSTER = (
        "cluster",
        "split one cluster (or the full catalogue) into sub-groups; "
        "supply partition_spec for a deterministic split by an exact metadata attribute "
        "(genre, runtime, release_year, director, vote_average, original_language), "
        "otherwise uses semantic embedding clustering optionally guided by concept",
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
        "no clustering is performed — use cluster afterwards to cluster the filtered set",
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


class DialogueMode(str, Enum):
    """Non-clustering intent modes handled directly by the coordinator.

    These do not produce a new cluster snapshot via the clustering agent.

    Attributes:
        RESET:       Clear all clustering — return to the unclustered state.
        GO_TO_BASE:  Navigate to the pre-computed ingest-time base clustering.
        EXPLAIN:     Explain why a movie belongs in a cluster.
        SMALL_TALK:  Casual, non-operational message.
    """

    def __new__(cls, value: str, description: str = "") -> "DialogueMode":
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj._description = description
        return obj

    RESET = (
        "reset",
        "return to unclustered state (before any clustering)",
    )
    GO_TO_BASE = (
        "go_to_base",
        "return to the pre-computed ingest-time clustering",
    )
    EXPLAIN = (
        "explain",
        "explain why a specific movie is in a particular cluster",
    )
    SMALL_TALK = (
        "small_talk",
        "casual message with no clustering operation needed",
    )
    UNDO = (
        "undo",
        "step back to the previous clustering snapshot, undoing the last operation",
    )

    @property
    def description(self) -> str:
        """One-line description of this mode for use in the intent prompt."""
        return self._description  # type: ignore[attr-defined]


class MetadataFilterLLM(BaseModel):
    """Wire schema for the metadata predicate the LLM emits for CROSS_FILTER actions."""
    genres: list[str] | None = None
    release_year_min: int | None = None
    release_year_max: int | None = None
    director: str | None = None


class PartitionBinLLM(BaseModel):
    """A single labelled bucket emitted by the LLM for numeric cluster (deterministic branch) actions."""
    label: str
    min: float | None = None
    max: float | None = None


class PartitionSpecLLM(BaseModel):
    """Wire schema for the partition specification the LLM emits for cluster (deterministic branch) actions."""
    attribute: str
    bins: list[PartitionBinLLM] | None = None


class IntentActionLLM(BaseModel):
    """Structured output for a single action within the intent classification LLM call."""
    mode: NavigationMode | DialogueMode
    concept: str | None = None
    merged_label: str | None = None
    target_cluster_id: str | None = None
    confidence: float = 1.0
    embedding_spaces: list[Modality] = [Modality.TEXT]
    metadata_filter: MetadataFilterLLM | None = None
    partition_spec: PartitionSpecLLM | None = None
    target_n_clusters: int | None = None


class IntentLLMResponse(BaseModel):
    """Structured output expected from the intent classification LLM call.

    ``reasoning`` is a chain-of-thought scratchpad filled before ``actions``.
    It is generated first so the model can resolve ambiguities (pronoun
    references, partition_by vs drill_down, compound requests) before committing
    to a structured output.  It is used only for debugging and is not forwarded
    to the coordinator.

    ``actions`` wraps an ordered list of actions so the model can express
    compound requests (e.g. reset then drill-down) as a single turn.
    Single-action requests are represented as a one-element list.
    """
    reasoning: str = ""
    actions: list[IntentActionLLM]


@dataclass(frozen=True, slots=True)
class IntentAction:
    """A single classified action within a user turn.

    Attributes:
        mode:              Classified intent mode (NavigationMode or DialogueMode).
        concept:           Semantic concept to apply (e.g. ``"surrealism"``).
                           Populated for drill_down; ``None`` otherwise.
        merged_label:      Label to give the resulting merged cluster.
                           Populated only for ``mode == merge``; ``None`` otherwise.
        target_cluster_id: UUID of the cluster to operate on for drill_down / merge /
                           explain / focus. None when operating on the full snapshot.
        confidence:        Model confidence in [0, 1].
        embedding_spaces:  Embedding spaces to fuse for this operation. Defaults to
                           ``[Modality.TEXT]``; includes ``Modality.TRAILER`` when the
                           user references visual style or tone.
        metadata_filter:   Metadata predicate for cross_filter; ``None`` otherwise.
        partition_spec:    Attribute and bins for partition_by; ``None`` otherwise.
        target_n_clusters: Exact cluster count requested by the Oracle for drill_down.
                           ``None`` when no count was specified (emergent HDBSCAN count
                           is used).  Values < 2 are discarded with a warning.
        reuse_concept_id:  UUID of a previously persisted concept whose normalized scores
                           should be reused for clustering.  Set by the coordinator when
                           the user is confirming a concept-axis proposal; never set by
                           the LLM directly.  When non-None the concept agent is skipped.
    """
    mode: NavigationMode | DialogueMode
    concept: str | None
    merged_label: str | None
    target_cluster_id: uuid.UUID | None
    confidence: float
    embedding_spaces: list[Modality]
    metadata_filter: MetadataFilter | None
    partition_spec: PartitionSpec | None
    target_n_clusters: int | None
    reuse_concept_id: uuid.UUID | None = None

    @classmethod
    def from_llm_action(cls, parsed: IntentActionLLM) -> "IntentAction":
        """
        Construct from a single Pydantic-validated LLM action object.

        Args:
            parsed: Pydantic-validated single action from the LLM payload.
        """
        target_id: uuid.UUID | None = None
        raw_target = parsed.target_cluster_id
        if raw_target:
            try:
                target_id = uuid.UUID(raw_target)
            except ValueError:
                log.warning("intent_invalid_cluster_id", extra={"raw": raw_target})

        metadata_filter: MetadataFilter | None = None
        if parsed.metadata_filter is not None:
            mf = parsed.metadata_filter
            metadata_filter = MetadataFilter(
                genres=mf.genres,
                release_year_min=mf.release_year_min,
                release_year_max=mf.release_year_max,
                director=mf.director,
            )

        partition_spec: PartitionSpec | None = None
        if parsed.partition_spec is not None:
            ps = parsed.partition_spec
            try:
                attr = PartitionAttribute(ps.attribute)
            except ValueError:
                log.warning("intent_invalid_partition_attribute", extra={"raw": ps.attribute})
                attr = None  # type: ignore[assignment]
            if attr is not None:
                bins = [PartitionBin(label=b.label, min=b.min, max=b.max) for b in (ps.bins or [])]
                partition_spec = PartitionSpec(attribute=attr, bins=bins or None)

        target_n_clusters: int | None = None
        if parsed.target_n_clusters is not None:
            if parsed.target_n_clusters < 2:
                log.warning(
                    "intent_invalid_cluster_count",
                    extra={"raw": parsed.target_n_clusters},
                )
            else:
                target_n_clusters = parsed.target_n_clusters

        return cls(
            mode=parsed.mode,
            concept=parsed.concept,
            merged_label=parsed.merged_label,
            target_cluster_id=target_id,
            confidence=parsed.confidence,
            embedding_spaces=parsed.embedding_spaces,
            metadata_filter=metadata_filter,
            partition_spec=partition_spec,
            target_n_clusters=target_n_clusters,
        )


@dataclass(frozen=True, slots=True)
class IntentResult:
    """
    Output of the Intent agent.

    Attributes:
        actions:     Ordered list of actions to execute for this turn. Most turns
                     produce a single action; compound requests (e.g. "drill down and
                     then recut") produce two or more.
        cost:        LLM cost in USD for this call.
        raw_intent:  Raw JSON string from the LLM for debugging.
    """
    actions: list[IntentAction]
    cost: float
    raw_intent: str

    @classmethod
    def from_llm_response(
        cls, parsed: IntentLLMResponse, raw_content: str, cost: float
    ) -> "IntentResult":
        """Construct from a structured LLM response.

        Maps each action through ``IntentAction.from_llm_action`` for UUID coercion
        and normalisation.

        Args:
            parsed:      Pydantic-validated LLM payload.
            raw_content: Raw response text for the ``raw_intent`` audit field.
            cost:        LLM call cost in USD.
        """
        return cls(
            actions=[IntentAction.from_llm_action(a) for a in parsed.actions],
            cost=cost,
            raw_intent=raw_content,
        )
