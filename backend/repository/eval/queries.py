import logging
import uuid
from decimal import Decimal

from backend.repository.connection import transaction
from backend.repository.eval.types import (
    JudgeScoreRead,
    SessionMetricsRead,
)

log = logging.getLogger(__name__)


def list_session_metrics_for_run(run_id: uuid.UUID) -> list[SessionMetricsRead]:
    """
    Return all session_metrics rows for sessions belonging to run_id.
    Joins session_metrics with sessions to include persona_id and ground_truth_id
    required for per-persona aggregation.
    Args:
        run_id: Run UUID to filter by.
    Returns:
        List of SessionMetricsRead, one per session that has metrics. Sessions
        without a session_metrics row are excluded.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                sm.session_id,
                s.persona_id,
                s.ground_truth_id,
                sm.converged,
                sm.turns_to_convergence,
                sm.avg_cognitive_load,
                sm.explicit_acceptance,
                sm.drift_events,
                sm.total_cost_usd,
                sm.precision_at_k,
                sm.recall_at_k,
                sm.ndcg_at_k
            FROM session_metrics sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE s.run_id = %s
            """,
            (run_id,),
        ).fetchall()

    return [
        SessionMetricsRead(
            session_id=r[0],
            persona_id=r[1],
            ground_truth_id=r[2],
            converged=r[3],
            turns_to_convergence=r[4],
            avg_cognitive_load=r[5],
            explicit_acceptance=r[6],
            drift_events=r[7],
            total_cost_usd=float(r[8]),
            precision_at_k=r[9],
            recall_at_k=r[10],
            ndcg_at_k=r[11],
        )
        for r in rows
    ]


def list_judge_scores_for_run(run_id: uuid.UUID) -> list[JudgeScoreRead]:
    """
    Return all judge_scores rows for sessions belonging to run_id.
    Joins judge_scores with sessions to include persona_id for per-persona grouping.
    Args:
        run_id: Run UUID to filter by.
    Returns:
        List of JudgeScoreRead across all sessions and all judge dimensions.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT js.session_id, s.persona_id, js.dimension, js.score
            FROM judge_scores js
            JOIN sessions s ON s.id = js.session_id
            WHERE s.run_id = %s
            """,
            (run_id,),
        ).fetchall()

    return [
        JudgeScoreRead(
            session_id=r[0],
            persona_id=r[1],
            dimension=r[2],
            score=r[3],
        )
        for r in rows
    ]


def count_sessions_per_run(run_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """
    Return the session count for each requested run_id.
    Args:
        run_ids: List of run UUIDs to count sessions for.
    Returns:
        Dict mapping run_id to session count. Runs with no sessions are absent.
    """
    if not run_ids:
        return {}

    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT run_id, COUNT(*) AS n
            FROM sessions
            WHERE run_id = ANY(%s)
            GROUP BY run_id
            """,
            (run_ids,),
        ).fetchall()

    return {r[0]: r[1] for r in rows}


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
    """
    Insert or update the session_metrics row for a session.
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
    """
    Append a judge_scores row.
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
