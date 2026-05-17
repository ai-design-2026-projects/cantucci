"""Orchestrator policy helpers — pure decision functions with no side effects.

All functions operate on already-fetched state and return simple values.
No DB access, no LLM calls.
"""

from backend.api.types import StepType, TurnDetail


def prior_questions(turns: list[TurnDetail]) -> list[str]:
    """Collect all prior clarifying-question texts in turn order.

    Args:
        turns: Prior turns in ascending turn_number order.

    Returns:
        List of assistant messages from ask-type turns.
    """
    return [
        t.assistant_message
        for t in turns
        if t.step_type == StepType.ask.value and t.assistant_message
    ]


def cluster_snapshot_to_spec(snapshot: "ClusterSnapshot") -> "ClusterSpec":
    """Convert a ClusterSnapshot (in-memory) to a ClusterSpec (DB input).

    Args:
        snapshot: In-memory cluster produced by the Cluster Agent.

    Returns:
        ClusterSpec suitable for ``api_sessions.snapshot_clusters``.
    """
    from backend.api.types import ClusterSpec
    return ClusterSpec(
        name=snapshot.name,
        description=snapshot.description,
        level=snapshot.level,
        centroid=None,
        parent_cluster_id=snapshot.parent_cluster_id,
        assignments=[(a.movie_id, a.score, a.excluded) for a in snapshot.assignments],
    )
