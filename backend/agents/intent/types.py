import logging
import uuid
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel

log = logging.getLogger(__name__)


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
class IntentResult:
    """Output of the Intent agent.

    Attributes:
        mode:             Classified navigation mode.
        concept:          Semantic concept to apply (e.g. ``"surrealism"``).
                          Populated for drill_down and recut; ``None`` otherwise.
        merged_label:     Label to give the resulting merged cluster.
                          Populated only for ``mode == merge``; ``None`` otherwise.
        target_cluster_id: UUID of the cluster to operate on for drill_down / merge / explain.
                           None when operating on the full cluster snapshot.
        confidence:       Model confidence in [0, 1].
        raw_intent:       Raw JSON string from the LLM for debugging.
    """
    mode: NavigationMode
    concept: str | None
    merged_label: str | None
    target_cluster_id: uuid.UUID | None
    confidence: float
    raw_intent: str

    @classmethod
    def from_llm_response(cls, parsed: BaseModel, raw_content: str) -> "IntentResult":
        """Construct from a structured LLM response.

        Normalises the raw ``mode`` string to ``NavigationMode`` (falls back to
        ``SMALL_TALK`` on unknown values) and parses ``target_cluster_id`` to
        a ``uuid.UUID`` (discards malformed values with a warning).

        Args:
            parsed:      Pydantic-validated LLM payload with ``mode``, ``concept``,
                         ``merged_label``, ``target_cluster_id``, and ``confidence`` fields.
            raw_content: Raw response text for the ``raw_intent`` audit field.
        """
        try:
            mode = NavigationMode(parsed.mode)  # type: ignore[attr-defined]
        except ValueError:
            log.warning("intent_unknown_mode", extra={"raw_mode": parsed.mode})  # type: ignore[attr-defined]
            mode = NavigationMode.SMALL_TALK

        target_id: uuid.UUID | None = None
        raw_target = parsed.target_cluster_id  # type: ignore[attr-defined]
        if raw_target:
            try:
                target_id = uuid.UUID(raw_target)
            except ValueError:
                log.warning("intent_invalid_cluster_id", extra={"raw": raw_target})

        return cls(
            mode=mode,
            concept=parsed.concept,  # type: ignore[attr-defined]
            merged_label=parsed.merged_label,  # type: ignore[attr-defined]
            target_cluster_id=target_id,
            confidence=parsed.confidence,  # type: ignore[attr-defined]
            raw_intent=raw_content,
        )
