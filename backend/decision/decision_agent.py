"""Decision Agent — mocked implementation.

Returns a hardcoded ``DecisionResult`` until the real LLM-driven
implementation is wired in (architecture.md §Decision Agent).

No DB writes. This module is read-only at runtime.
"""

import logging
from pathlib import Path
from uuid import UUID

from backend.llm.prompts import make_prompt_loader
from backend.models.clusters import ClusterSnapshot
from backend.models.decision import DecisionAction, DecisionResult

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent / "prompts")


def decide(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_query: str,
    clusters: list[ClusterSnapshot],
    config_hash: str,
    model_version: str,
) -> DecisionResult:
    """Return a routing decision for the current turn (not yet implemented).

    Args:
        session_id:    UUID of the current session.
        run_id:        UUID of the parent run.
        turn_id:       UUID of the current turn.
        turn_number:   1-based turn index within the session.
        user_query:    Oracle's message for this turn.
        clusters:      Current cluster snapshots (empty until Cluster Agent
                       is wired in).
        config_hash:   SHA-256 prefix of the session's YAML config snapshot.
        model_version: LLM model string stored on the session row.

    Returns:
        A ``DecisionResult`` with ``action=recommend`` and zero entropy until
        the real implementation replaces this stub.
    """
    log.warning("decision agent not yet implemented")
    return DecisionResult(
        action=DecisionAction.recommend,
        best_cluster_id=None,
        rationale="[mock] decision agent placeholder",
        entropy_score=0.0,
    )
