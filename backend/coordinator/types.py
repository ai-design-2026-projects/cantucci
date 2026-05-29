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


@dataclass(frozen=True, slots=True)
class ClusterDraft:
    """A cluster to be written to the DB as part of a new cluster snapshot.

    Attributes:
        label:              Human-readable label, or None when the LLM labeler will generate it.
        summary:            One-sentence description, or None to trigger LLM labeling.
        exemplar_movie_ids: Top movie IDs by probability.
        parent_cluster_id:  Source cluster UUID for drill-down operations.
        memberships:        List of (movie_id, probability) pairs.
        concept_score:      Probability-weighted mean concept score for this cluster, set only
                            for concept-driven drill_down so the labeller can order clusters
                            along the concept axis. None for all other operations.
    """
    label: str | None
    summary: str | None
    exemplar_movie_ids: list[int]
    parent_cluster_id: uuid.UUID | None
    memberships: list[tuple[int, float]] = field(default_factory=list)
    concept_score: float | None = None


@dataclass(frozen=True, slots=True)
class ClusterSnapshotDraft:
    """A complete cluster snapshot ready to be persisted.

    Attributes:
        operation: Operation name (e.g. ``"drill_down"``, ``"merge"``, ``"cross_filter"``).
        params:    Replayability parameters dict.
        clusters:  List of cluster drafts.
        warning:   Optional human-readable notice about the operation result (e.g. truncation).
                   Not included in ``params`` — does not affect the content-address cache hash.
    """
    operation: str
    params: dict
    clusters: list[ClusterDraft] = field(default_factory=list)
    warning: str | None = None
