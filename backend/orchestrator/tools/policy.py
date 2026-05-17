"""Orchestrator policy helpers — pure decision functions with no side effects.

All functions operate on already-fetched state and return simple values.
No DB access, no LLM calls.
"""

from dataclasses import dataclass

from backend.api.types import ClusterSnapshot, SessionFull, StepType, TurnDetail


@dataclass(frozen=True)
class RetrievalDecision:
    """Whether to run fresh retrieval and what query to use.

    Attributes:
        retrieve: True when the Cluster Agent should run a new vector search.
        query:    The query to pass to retrieval; None when retrieve is False.
    """

    retrieve: bool
    query: str | None


def should_retrieve(full: SessionFull, user_message: str) -> RetrievalDecision:
    """Decide whether to run retrieval this turn and what query to use.

    Policy:
    - Always retrieve on the first turn using the current oracle message.
    - Reuse prior candidates on all other turns. Drift confirmation is handled
      by the convergence gate, which sets retrieval_override on drift_confirmed.

    Args:
        full:         Full session state for the turn about to run.
        user_message: The oracle's message for the current turn.

    Returns:
        A RetrievalDecision with retrieve=True and a query string, or
        retrieve=False and query=None to reuse prior candidates.
    """
    if not full.turns:
        return RetrievalDecision(retrieve=True, query=user_message)

    return RetrievalDecision(retrieve=False, query=None)


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
