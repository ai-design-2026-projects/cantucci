"""Orchestrator feedback helpers — oracle message classification and profile extraction.

MVP heuristic classifiers; an LLM-based ``f_next_state`` classifier is a future
iteration described in docs/specifications/problem_statement.md §4.
"""

from backend.api.types import ClusterSnapshot, StepType, TurnDetail
from backend.decision.types import DecisionResult
from typing import Any

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


def extract_preference_profile(
    turns: list[TurnDetail],
    user_message: str,
    clusters: list[ClusterSnapshot] | None = None,
    decision: DecisionResult | None = None,
) -> dict[str, Any]:
    """Build a minimal preference profile from the conversation history.

    When called before the pipeline runs (clusters=None, decision=None), only
    ``oracle_constraints`` is populated. When called at convergence with the
    full agent outputs, ``final_cluster_name`` and ``final_cluster_description``
    are also set.

    Args:
        turns:        All prior turns (not including the current one).
        user_message: Oracle's message for the current turn.
        clusters:     Current cluster snapshots, or None if not yet computed.
        decision:     Decision Agent output for the current turn, or None.

    Returns:
        Dict with keys ``oracle_constraints``, ``final_cluster_name``,
        ``final_cluster_description``.
    """
    constraints = [t.user_message for t in turns if t.step_type == StepType.ask.value]
    constraints.append(user_message)
    best: ClusterSnapshot | None = None
    if decision is not None and decision.best_cluster_id and clusters:
        best = next((c for c in clusters if c.id == decision.best_cluster_id), None)
    if best is None and clusters:
        best = clusters[0]
    return {
        "oracle_constraints": constraints,
        "final_cluster_name": best.name if best else "unknown",
        "final_cluster_description": best.description if best else None,
    }
