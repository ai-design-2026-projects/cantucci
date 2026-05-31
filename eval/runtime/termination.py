"""Session termination status inference."""


def infer_termination_status(
    oracle_decision: str,
    oracle_rating: int | None,
    hit_budget: bool,
) -> str:
    """Infer a terminal status string from the oracle's final decision and rating.

    The oracle's ``session_rating`` is the authoritative signal for whether the
    session was successful.  Concept-string comparison against the ground-truth
    trajectory is intentionally omitted — GT concepts rarely match executed
    concepts verbatim, so such a comparison would produce false misbehaviour
    classifications.

    Args:
        oracle_decision: ``"stop"`` or ``"continue"``.
        oracle_rating:   Oracle's self-reported session quality (1–5), present
                         only when ``oracle_decision == "stop"``.
        hit_budget:      ``True`` when the runner exhausted ``max_turns`` without
                         the oracle stopping.

    Returns:
        One of: ``"finished_trajectory"``, ``"finished_misbehaviour"``,
        ``"finished_budget"``.
    """
    if hit_budget:
        return "finished_budget"

    if oracle_decision == "stop":
        if oracle_rating is not None and oracle_rating >= 4:
            return "finished_trajectory"
        return "finished_misbehaviour"

    return "finished_budget"
