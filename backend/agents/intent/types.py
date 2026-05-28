import logging
import uuid
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel

from backend.agents.clustering.types import MetadataFilter, Modality, NavigationMode, PartitionAttribute, PartitionBin, PartitionSpec

log = logging.getLogger(__name__)


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
    """A single labelled bucket emitted by the LLM for numeric PARTITION_BY actions."""
    label: str
    min: float | None = None
    max: float | None = None


class PartitionSpecLLM(BaseModel):
    """Wire schema for the partition specification the LLM emits for PARTITION_BY actions."""
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


class IntentLLMResponse(BaseModel):
    """Structured output expected from the intent classification LLM call.

    Wraps an ordered list of actions so the model can express compound requests
    (e.g. reset then drill-down) as a single turn.  Single-action requests are
    represented as a one-element list, preserving backward-compatible behaviour.
    """
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
    """
    mode: NavigationMode | DialogueMode
    concept: str | None
    merged_label: str | None
    target_cluster_id: uuid.UUID | None
    confidence: float
    embedding_spaces: list[Modality]
    metadata_filter: MetadataFilter | None
    partition_spec: PartitionSpec | None

    @classmethod
    def from_llm_action(cls, parsed: IntentActionLLM) -> "IntentAction":
        """Construct from a single Pydantic-validated LLM action object.

        Parses ``target_cluster_id`` to a ``uuid.UUID`` (discards malformed
        values with a warning). Converts ``MetadataFilterLLM`` to the internal
        ``MetadataFilter`` dataclass.

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

        return cls(
            mode=parsed.mode,
            concept=parsed.concept,
            merged_label=parsed.merged_label,
            target_cluster_id=target_id,
            confidence=parsed.confidence,
            embedding_spaces=parsed.embedding_spaces,
            metadata_filter=metadata_filter,
            partition_spec=partition_spec,
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
