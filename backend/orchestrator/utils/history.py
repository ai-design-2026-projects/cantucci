"""
Pure history-inspection helpers for the orchestrator.
Functions here only read from already-fetched session state. No DB access, no
LLM calls, no side effects. They exist to keep the per-turn flow readable —
each call answers a single question about the prior turns.
"""
from backend.orchestrator.domain import StepType
from backend.repository.sessions import SessionRow, TurnRow


def last_clustered_turn(turns: list[TurnRow]) -> TurnRow | None:
    """Most recent turn that persisted a non-empty cluster set, or None.

    Walks the history in reverse so a clarify_drift turn (which carries no
    clusters) does not block refinement from reaching the show turn that
    came before it. Returns None only on the truly-first clustered turn of
    a session — that is the single point at which retrieval is allowed to
    rebuild the cluster set from scratch.
    """
    for t in reversed(turns):
        if t.clusters:
            return t
    return None


def prior_questions(turns: list[TurnRow]) -> list[str]:
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


def recommended_titles_from_last_show(full: SessionRow) -> list[str]:
    """Titles included in the most recent show-turn's recommendation.
    Used by the state gate (``recommended_last_turn`` kwarg) so the LLM can
    detect "I've already seen these" replies and route to re_retrieve.
    Args:
        full: Loaded session state.
    Returns:
        Ordered list of film titles from the latest show turn, or [] if the
        last turn was not a show turn or no turns exist yet.
    """
    if not full.turns:
        return []
    last = full.turns[-1]
    if last.step_type != StepType.show.value:
        return []
    titles: list[str] = []
    for c in last.clusters:
        for a in c.assignments:
            if not a.excluded and a.title:
                titles.append(a.title)
    return titles

__all__ = [
    "last_clustered_turn",
    "prior_questions",
    "recommended_titles_from_last_show",
]
