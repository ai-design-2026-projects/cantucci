"""Orchestrator policy helpers — pure decision functions with no side effects.

All functions operate on already-fetched state and return simple values.
No DB access, no LLM calls.
"""

from backend.models.clusters import ClusterSnapshot
from backend.models.retrieval import SessionFull, TurnDetail
from backend.models.sessions import StepType


def collect_prior_candidates(turn: TurnDetail) -> list[int]:
    """Return all movie IDs from the cluster assignments of a prior turn.

    Includes excluded assignments so the candidate pool is not artificially
    narrowed by the previous turn's soft-assignment threshold.

    Args:
        turn: The most recent completed turn with cluster snapshots.

    Returns:
        Deduplicated list of TMDB movie IDs, in assignment order.
    """
    seen: set[int] = set()
    ids: list[int] = []
    for c in turn.clusters:
        for a in c.assignments:
            if a.movie_id not in seen:
                seen.add(a.movie_id)
                ids.append(a.movie_id)
    return ids


def is_duplicate_question(text: str, turns: list[TurnDetail]) -> bool:
    """Return True if *text* exactly matches a prior ask-type assistant message.

    The Orchestrator is the authoritative deduplication source per architecture.md.

    Args:
        text:  Proposed question text from the Ambiguity Resolver.
        turns: Prior turns in ascending turn_number order.

    Returns:
        True if the question has already been asked.
    """
    for t in turns:
        if t.step_type == StepType.ask.value and t.assistant_message == text:
            return True
    return False


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
    from backend.models.clusters import ClusterSpec
    return ClusterSpec(
        name=snapshot.name,
        description=snapshot.description,
        level=snapshot.level,
        centroid=None,
        parent_cluster_id=snapshot.parent_cluster_id,
        assignments=[(a.movie_id, a.score, a.excluded) for a in snapshot.assignments],
    )
