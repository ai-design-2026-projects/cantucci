import uuid
from dataclasses import dataclass
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


@dataclass
class IntentResult:
    """Output of the Intent agent.

    Attributes:
        mode:             Classified navigation mode.
        dimension:        Semantic dimension or concept to apply (e.g. ``"surrealism"``).
                          None for non-concept modes (merge, reset, small_talk).
        target_cluster_id: UUID of the cluster to operate on for drill_down / merge / explain.
                           None when operating on the full cluster snapshot.
        confidence:       Model confidence in [0, 1].
        raw_intent:       Raw JSON string from the LLM for debugging.
    """
    mode: NavigationMode
    dimension: str | None
    target_cluster_id: uuid.UUID | None
    confidence: float
    raw_intent: str
