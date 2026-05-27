import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TurnTrace:
    """Structured per-turn trace of intent classification and execution results.

    Populated by the coordinator and consumed by eval/baseline runners to persist
    turn_intents rows. Live HTTP routing ignores this field entirely.

    Attributes:
        modes:             Ordered list of NavigationMode/DialogueMode value strings.
        concepts:          Parallel list of semantic concept strings (None if absent).
        target_cluster_ids: Parallel list of target cluster UUIDs (None if absent).
        confidence:        Minimum confidence across all classified actions.
        clarifier_fired:   True if the clarifier gate interrupted dispatch this turn.
        raw_intent:        Raw intent JSON string from IntentResult.raw_intent.
        suggestion:        Responder suggestion text, or None.
        explanation:       Explanation agent output text, or None.
    """
    modes: list[str]
    concepts: list[str | None]
    target_cluster_ids: list[uuid.UUID | None]
    confidence: float
    clarifier_fired: bool
    raw_intent: str
    suggestion: str | None
    explanation: str | None


@dataclass(frozen=True, slots=True)
class CoordinatorResult:
    """Output of a single Coordinator.handle_message call.

    Attributes:
        reply_text:          Text to send back to the user.
        cluster_snapshot_id: UUID of the active cluster snapshot after this message.
        turn_cost_usd:       Total LLM cost incurred during this turn, in USD.
        suggestion:          Optional follow-up suggestion from the suggester agent.
                             None on clarification paths, small_talk, explain, and reset.
        turn_trace:          Structured trace for eval/baseline runners to persist.
                             None when the trace is not needed (e.g. live HTTP path
                             doesn't read it, but it is always populated by the coordinator).
    """

    reply_text: str
    cluster_snapshot_id: uuid.UUID
    turn_cost_usd: float = 0.0
    suggestion: str | None = None
    turn_trace: TurnTrace | None = None


def sentinel_cluster_snapshot_id() -> uuid.UUID:
    """Return a zero UUID as a sentinel when no cluster snapshot exists yet."""
    return uuid.UUID("00000000-0000-0000-0000-000000000000")
