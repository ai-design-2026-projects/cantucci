import logging
import uuid
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel

log = logging.getLogger(__name__)


class Modality(str, Enum):
    """Embedding spaces available for runtime distance computation.

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


class IntentActionLLM(BaseModel):
    """Structured output for a single action within the intent classification LLM call."""
    navigationMode: NavigationMode
    concept: str | None = None
    merged_label: str | None = None
    target_cluster_id: str | None = None
    confidence: float = 1.0
    embedding_spaces: list[Modality] = [Modality.TEXT]


class IntentLLMResponse(BaseModel):
    """Structured output expected from the intent classification LLM call.

    Wraps an ordered list of actions so the model can express compound requests
    (e.g. drill-down then recut) as a single turn.  Single-action requests are
    represented as a one-element list, preserving backward-compatible behaviour.
    """
    actions: list[IntentActionLLM]


@dataclass(frozen=True, slots=True)
class IntentAction:
    """A single classified action within a user turn.

    Attributes:
        navigationMode:    Classified navigation mode.
        concept:           Semantic concept to apply (e.g. ``"surrealism"``).
                           Populated for drill_down and recut; ``None`` otherwise.
        merged_label:      Label to give the resulting merged cluster.
                           Populated only for ``navigationMode == merge``; ``None`` otherwise.
        target_cluster_id: UUID of the cluster to operate on for drill_down / merge / explain.
                           None when operating on the full cluster snapshot.
        confidence:        Model confidence in [0, 1].
        embedding_spaces:  Embedding spaces to fuse for this operation. Defaults to
                           ``[Modality.TEXT]``; includes ``Modality.TRAILER`` when the
                           user references visual style or tone.
    """
    navigationMode: NavigationMode
    concept: str | None
    merged_label: str | None
    target_cluster_id: uuid.UUID | None
    confidence: float
    embedding_spaces: list[Modality]

    @classmethod
    def from_llm_action(cls, parsed: IntentActionLLM) -> "IntentAction":
        """Construct from a single Pydantic-validated LLM action object.

        Parses ``target_cluster_id`` to a ``uuid.UUID`` (discards malformed
        values with a warning).

        Args:
            parsed: Pydantic-validated single action from the LLM payload.
        """
        target_id: uuid.UUID | None = None
        raw_target = parsed.target_cluster_id  # type: ignore[attr-defined]
        if raw_target:
            try:
                target_id = uuid.UUID(raw_target)
            except ValueError:
                log.warning("intent_invalid_cluster_id", extra={"raw": raw_target})

        return cls(
            navigationMode=parsed.navigationMode,  # type: ignore[attr-defined]
            concept=parsed.concept,  # type: ignore[attr-defined]
            merged_label=parsed.merged_label,  # type: ignore[attr-defined]
            target_cluster_id=target_id,
            confidence=parsed.confidence,  # type: ignore[attr-defined]
            embedding_spaces=parsed.embedding_spaces,  # type: ignore[attr-defined]
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
            actions=[IntentAction.from_llm_action(a) for a in parsed.actions],  # type: ignore[attr-defined]
            cost=cost,
            raw_intent=raw_content,
        )
