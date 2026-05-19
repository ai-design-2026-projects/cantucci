"""
Write evaluation results: session_metrics and judge_scores.

These are written by the eval harness after a session completes; never by the
live conversational loop.
"""

import logging
import uuid
from decimal import Decimal

from backend.api.db import transaction

log = logging.getLogger(__name__)


def upsert_session_metrics(
    session_id: uuid.UUID,
    converged: bool,
    turns_to_convergence: int | None = None,
    avg_cognitive_load: float | None = None,
    explicit_acceptance: bool = False,
    drift_events: int = 0,
    total_input_tokens: int = 0,
    total_output_tokens: int = 0,
    total_cost_usd: Decimal = Decimal("0"),
    precision_at_k: float | None = None,
    recall_at_k: float | None = None,
    ndcg_at_k: float | None = None,
) -> None:
    """Insert or update the session_metrics row for a session.

    Safe to call multiple times for the same session; later calls overwrite
    earlier values so metrics can be recomputed after post-processing.

    Args:
        session_id: Session to attach metrics to.
        converged: Whether the session reached convergence.
        turns_to_convergence: Turn number when convergence was declared (None if abandoned).
        avg_cognitive_load: Mean cognitive load per turn (titles+clusters+question complexity).
        explicit_acceptance: True if convergence was triggered by an explicit oracle signal.
        drift_events: Count of preference drift events detected by the Orchestrator.
        total_input_tokens: Sum of input tokens across all LLM calls in the session.
        total_output_tokens: Sum of output tokens across all LLM calls.
        total_cost_usd: Estimated API cost for the session.
        precision_at_k: Precision@K of the final recommendation vs ground-truth film set.
        recall_at_k: Recall@K of the final recommendation vs ground-truth film set.
        ndcg_at_k: NDCG@K of the final recommendation vs ground-truth film set.
    """
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO session_metrics
                (session_id, converged, turns_to_convergence, avg_cognitive_load,
                 explicit_acceptance, drift_events, total_input_tokens,
                 total_output_tokens, total_cost_usd, computed_at,
                 precision_at_k, recall_at_k, ndcg_at_k)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                converged              = EXCLUDED.converged,
                turns_to_convergence   = EXCLUDED.turns_to_convergence,
                avg_cognitive_load     = EXCLUDED.avg_cognitive_load,
                explicit_acceptance    = EXCLUDED.explicit_acceptance,
                drift_events           = EXCLUDED.drift_events,
                total_input_tokens     = EXCLUDED.total_input_tokens,
                total_output_tokens    = EXCLUDED.total_output_tokens,
                total_cost_usd         = EXCLUDED.total_cost_usd,
                computed_at            = NOW(),
                precision_at_k         = EXCLUDED.precision_at_k,
                recall_at_k            = EXCLUDED.recall_at_k,
                ndcg_at_k              = EXCLUDED.ndcg_at_k
            """,
            (
                session_id, converged, turns_to_convergence, avg_cognitive_load,
                explicit_acceptance, drift_events, total_input_tokens,
                total_output_tokens, total_cost_usd,
                precision_at_k, recall_at_k, ndcg_at_k,
            ),
        )
    log.debug("upserted session_metrics for session %s", session_id)


def write_judge_score(
    session_id: uuid.UUID,
    dimension: str,
    score: int,
    judge_model: str,
    judge_prompt_hash: str,
    rationale: str | None = None,
) -> uuid.UUID:
    """Append a judge_scores row.

    Idempotent per (session_id, dimension, judge_prompt_hash) — inserting the
    same row twice raises IntegrityError rather than creating a duplicate.

    Args:
        session_id: Session that was scored.
        dimension: One of clustering_coherence | question_quality | profile_fidelity.
        score: Integer 1–5.
        judge_model: Model identifier used for the judge call.
        judge_prompt_hash: SHA-256 hex of the judge prompt file.
        rationale: One-sentence rationale returned by the judge.

    Returns:
        UUID of the inserted row.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO judge_scores
                (session_id, dimension, score, rationale,
                 judge_model, judge_prompt_hash)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (session_id, dimension, score, rationale,
             judge_model, judge_prompt_hash),
        ).fetchone()

    score_id: uuid.UUID = row[0]
    log.debug(
        "judge_score %s session=%s dimension=%s score=%d",
        score_id, session_id, dimension, score,
    )
    return score_id
