import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from backend.coordinator.types import TurnTrace


class BaselineCluster(BaseModel):
    """One cluster in the single-call baseline output.

    Attributes:
        label:    Short descriptive name for the cluster.
        summary:  One-sentence description of the films in this group.
        film_ids: TMDB integer IDs of films assigned to this cluster.
    """

    label: str
    summary: str
    film_ids: list[int]


class BaselineResponse(BaseModel):
    """Full output of a single baseline LLM call.

    The LLM produces a conversational reply, declares the navigation operation it
    performed, names the concept it used to organise films, and emits the complete
    resulting cluster grouping — all in one JSON object.

    Attributes:
        reply:     Conversational reply to send back to the oracle.
        operation: Navigation operation performed (one of the five NavigationMode values).
        concept:   Human-readable concept name used to organise the films.
                   Set for cluster operations; may be None for purely structural ops
                   (merge, focus, exclude, cross_filter).
        clusters:  Complete resulting cluster grouping after this turn.  Every film_id
                   must be drawn from the input film list passed in the prompt.
    """

    reply: str
    operation: Literal["cluster", "merge", "focus", "cross_filter", "exclude"]
    concept: str | None = None
    clusters: list[BaselineCluster]


@dataclass(frozen=True, slots=True)
class SystemTurnResult:
    """Output of one system turn, common across all experimental conditions.

    Attributes:
        reply_text:          Text to send back to the oracle.
        cluster_snapshot_id: UUID of the active cluster snapshot after this turn.
        turn_cost_usd:       LLM cost incurred during this turn.
        suggestion:          Optional follow-up suggestion text.
        turn_trace:          Structured intent trace for turn_intents persistence.
    """

    reply_text: str
    cluster_snapshot_id: uuid.UUID
    turn_cost_usd: float = 0.0
    suggestion: str | None = None
    turn_trace: TurnTrace | None = None
