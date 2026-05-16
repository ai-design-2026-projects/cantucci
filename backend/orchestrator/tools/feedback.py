"""Orchestrator feedback helpers — oracle message classification.

MVP heuristic classifier for feedback type. Profile extraction has moved to
backend.profile.profile_agent (LLM-based, run at the end of each turn).
"""

from backend.api.types import StepType, TurnDetail
from backend.decision.types import DecisionResult

_NEGATIVE_LEXICON = frozenset({
    "no", "not", "wrong", "don't", "doesn't", "didn't", "never", "nothing",
    "hate", "dislike", "avoid", "terrible", "awful", "bad", "nope", "neither",
})


def classify_feedback(
    prior_turns: list[TurnDetail],
    user_message: str,
    decision: DecisionResult,
) -> tuple[str, str, str | None]:
    """Return (feedback_level, feedback_type, target_id) for the current oracle message.

    MVP heuristic: first turn is a global constraint; responses to ask-type turns
    are classified as accept or reject based on lexical cues; all others are
    global constraints. An LLM-based classifier (``f_next_state``) is a future
    iteration.

    Args:
        prior_turns:  All turns before the current one.
        user_message: Oracle's message for the current turn.
        decision:     Decision Agent output (for best_cluster_id).

    Returns:
        Three-tuple of (feedback_level, feedback_type, target_id).
    """
    if not prior_turns:
        return "global", "constraint", None
    last_turn = prior_turns[-1]
    if last_turn.step_type == StepType.ask.value:
        words = set(user_message.lower().split())
        target = str(decision.best_cluster_id) if decision.best_cluster_id else None
        if words & _NEGATIVE_LEXICON:
            return "cluster", "reject", target
        return "cluster", "accept", target
    return "global", "constraint", None
