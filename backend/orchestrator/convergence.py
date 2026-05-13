from backend.orchestrator.tools.policy import SessionFull, StepType, StepType
from backend.api.types import TurnDetail


def should_retrieve(full: SessionFull) -> bool:
    """Return True if the Cluster Agent should run a fresh vector search this turn.

    Policy: always retrieve on the first turn;

    """
    if not full.turns:
        return True
    return False

def convergence_policy(turns: list[TurnDetail], convergence_turns: int) -> bool:
    """Return True when the last *convergence_turns* steps were all show-type.
    It should be an llm
    Simple policy: the oracle has seen the recommendation without issuing a
    corrective step for *convergence_turns* consecutive turns. LLM-driven
    preference-stability detection is a future iteration.

    Args:
        turns:             Prior turns in ascending turn_number order.
        convergence_turns: Number of consecutive show turns required.

    Returns:
        True if convergence criterion is met.
    """
    recent_show = [t for t in turns if t.step_type == StepType.show.value]
    return len(recent_show) >= convergence_turns