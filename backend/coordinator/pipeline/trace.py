import uuid

from backend.agents.intent.types import DialogueMode, IntentAction, IntentResult
from backend.agents.responder.types import SuggestionResult
from backend.coordinator.types import TurnTrace


def extract_trace_fields(
    intent: IntentResult,
) -> tuple[list[str], list[str | None], list[uuid.UUID | None], float, str]:
    """Extract per-turn trace metadata from the intent result.

    Args:
        intent: Classified intent with one or more actions.

    Returns:
        Tuple of (modes, concepts, target_cluster_ids, min_confidence, raw_intent).
    """
    return (
        [a.mode.value for a in intent.actions],
        [a.concept for a in intent.actions],
        [a.target_cluster_id for a in intent.actions],
        min((a.confidence for a in intent.actions), default=1.0),
        intent.raw_intent,
    )


def build_trace(
    trace_modes: list[str],
    trace_concepts: list[str | None],
    trace_targets: list[uuid.UUID | None],
    trace_confidence: float,
    trace_raw: str,
    clarifier_fired: bool,
    suggestion: SuggestionResult | None,
    reply_fragments: list[str],
    intent_actions: list[IntentAction],
) -> TurnTrace:
    """Construct a ``TurnTrace`` for the completed turn.

    Handles both the early-return (low-confidence gate) and normal dispatch paths.
    When ``clarifier_fired`` is True (either path), explanation and suggestion are
    always ``None`` because no clustering operation completed this turn.

    Args:
        trace_modes:      Mode value strings from intent actions.
        trace_concepts:   Concept strings (parallel to modes).
        trace_targets:    Target cluster UUIDs (parallel to modes).
        trace_confidence: Minimum confidence across all actions.
        trace_raw:        Raw intent JSON string.
        clarifier_fired:  True when this turn ended by asking a clarifying or confirming
                          question — covers the low-confidence gate (early return) and any
                          in-dispatch confirmation prompt that called ``mark_awaiting``.
        suggestion:       Suggester result (``None`` on the clarifier path).
        reply_fragments:  Per-action reply texts (empty on the clarifier path).
        intent_actions:   Classified actions (used to extract the explain text).

    Returns:
        ``TurnTrace`` for persistence by eval/baseline runners.
    """
    explanation_text: str | None = None
    if not clarifier_fired:
        for i, action in enumerate(intent_actions):
            if action.mode == DialogueMode.EXPLAIN and i < len(reply_fragments):
                explanation_text = reply_fragments[i]
                break
    return TurnTrace(
        modes=trace_modes,
        concepts=trace_concepts,
        target_cluster_ids=trace_targets,
        confidence=trace_confidence,
        clarifier_fired=clarifier_fired,
        raw_intent=trace_raw,
        suggestion=suggestion.text if suggestion else None,
        explanation=explanation_text,
    )
