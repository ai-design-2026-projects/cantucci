"""Session termination status inference."""


def infer_termination_status(
    oracle_decision: str,
    evolution_trace: list[dict],
    ground_truth_operations: list[dict],
    hit_budget: bool,
) -> str:
    """Infer a terminal status string from the oracle's final decision.

    Compares the set of executed ``(op, concept)`` pairs derived from the
    evolution trace against the ground truth operation set.

    Args:
        oracle_decision:          ``"stop"`` or ``"continue"``.
        evolution_trace:          List of ``{turn, modes, concepts}`` dicts accumulated
                                  during the session.
        ground_truth_operations:  GT operations list (dicts with ``op`` and ``concept``).
        hit_budget:               ``True`` when the runner exhausted ``max_turns`` without
                                  the oracle stopping.

    Returns:
        One of: ``"finished_trajectory"``, ``"finished_misbehaviour"``, ``"finished_budget"``.
    """
    if hit_budget:
        return "finished_budget"

    if oracle_decision == "stop":
        executed_set = {
            (mode, concept.strip().lower())
            for entry in evolution_trace
            for mode, concept in zip(entry["modes"], entry["concepts"])
        }
        gt_set = {(op["op"], op["concept"].strip().lower()) for op in ground_truth_operations}
        all_done = gt_set.issubset(executed_set)
        return "finished_trajectory" if all_done else "finished_misbehaviour"

    return "finished_budget"
