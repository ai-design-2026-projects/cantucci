"""
Read-side query for retrieving a complete session snapshot.

get_session_full — complete state snapshot for one session (turns, clusters,
                   assignments, feedback, metrics, judge scores). Used for replay.

Run-level aggregation with confidence intervals is handled by backend/eval/aggregator.py.
"""

import logging
import uuid
from typing import Any

from backend.api.db import transaction
from backend.api.types import (
    ClusterAssignment,
    ClusterRow,
    FeedbackRow,
    JudgeScoreRow,
    SessionMetricsRow,
    SessionRow,
    TurnRow,
)

log = logging.getLogger(__name__)


def get_session_full(session_id: uuid.UUID) -> SessionRow:
    """
    Retrieve from the DB the complete state of a session, including all turns, clusters, assignments,
    oracle feedback, and metrics.
    Args:
        session_id: UUID of the session.
    Returns:
        SessionRow with all nested data.
    Raises:
        ValueError: If the session does not exist.
    """
    with transaction() as conn:
        sess_row = conn.execute(
            """
            SELECT id, run_id, seed, config_hash, model_version,
                   status, preference_profile,
                   created_at, updated_at, max_turns
            FROM sessions
            WHERE id = %s
            """,
            (session_id,),
        ).fetchone()

        # Check existence before proceeding to avoid doing extra work for a non-existent session.
        if sess_row is None:
            raise ValueError(f"session {session_id} not found")
        
        # get all the turns for this session, ordered by turn_number
        turn_rows = conn.execute(
            """
            SELECT id, turn_number, user_message, assistant_message,
                   step_type, converged, created_at
            FROM turns
            WHERE session_id = %s
            ORDER BY turn_number
            """,
            (session_id,),
        ).fetchall()
        turn_ids = [r[0] for r in turn_rows]

        # Get all clusters and their assignments for this session's turns
        cluster_rows: list[Any] = []
        assignment_rows: list[Any] = []
        if turn_ids:
            cluster_rows = conn.execute(
                """
                SELECT id, turn_id, name, description, level, parent_cluster_id
                FROM clusters
                WHERE turn_id = ANY(%s)
                ORDER BY turn_id, level, name
                """,
                (turn_ids,),
            ).fetchall()

            cluster_ids = [r[0] for r in cluster_rows]
            if cluster_ids:
                assignment_rows = conn.execute(
                    """
                    SELECT cluster_id, movie_id, score, excluded
                    FROM cluster_assignments
                    WHERE cluster_id = ANY(%s)
                    """,
                    (cluster_ids,),
                ).fetchall()

        # Oracle feedback
        feedback_rows = conn.execute(
            """
            SELECT id, turn_id, feedback_level, feedback_type, target_id, content
            FROM oracle_feedback
            WHERE session_id = %s
            ORDER BY created_at
            """,
            (session_id,),
        ).fetchall()

        # Metrics
        metrics_row = conn.execute(
            """
            SELECT session_id, converged, turns_to_convergence, avg_cognitive_load,
                   explicit_acceptance, drift_events, total_input_tokens,
                   total_output_tokens, total_cost_usd,
                   precision_at_k, recall_at_k, ndcg_at_k
            FROM session_metrics
            WHERE session_id = %s
            """,
            (session_id,),
        ).fetchone()

        # Judge scores
        judge_rows = conn.execute(
            """
            SELECT id, session_id, dimension, score, rationale, judge_model, judge_prompt_hash
            FROM judge_scores
            WHERE session_id = %s
            ORDER BY created_at
            """,
            (session_id,),
        ).fetchall()

    # Assemble nested structure
    assignments_by_cluster: dict[uuid.UUID, list[ClusterAssignment]] = {}
    for r in assignment_rows:
        assignments_by_cluster.setdefault(r[0], []).append(
            ClusterAssignment(movie_id=r[1], score=r[2], excluded=r[3])
        )

    clusters_by_turn: dict[uuid.UUID, list[ClusterRow]] = {}
    for r in cluster_rows:
        clusters_by_turn.setdefault(r[1], []).append(
            ClusterRow(
                id=r[0], name=r[2], description=r[3], level=r[4],
                parent_cluster_id=r[5],
                assignments=assignments_by_cluster.get(r[0], []),
            )
        )

    turns = [
        TurnRow(
            id=r[0], turn_number=r[1], user_message=r[2],
            assistant_message=r[3], step_type=r[4], converged=r[5],
            clusters=clusters_by_turn.get(r[0], []),
            created_at=r[6],
        )
        for r in turn_rows
    ]

    feedback = [
        FeedbackRow(
            id=r[0], turn_id=r[1], feedback_level=r[2],
            feedback_type=r[3], target_id=r[4], content=r[5],
        )
        for r in feedback_rows
    ]

    metrics = None
    if metrics_row is not None:
        metrics = SessionMetricsRow(
            session_id=metrics_row[0], converged=metrics_row[1],
            turns_to_convergence=metrics_row[2], avg_cognitive_load=metrics_row[3],
            explicit_acceptance=metrics_row[4], drift_events=metrics_row[5],
            total_input_tokens=metrics_row[6], total_output_tokens=metrics_row[7],
            total_cost_usd=metrics_row[8],
            precision_at_k=metrics_row[9], recall_at_k=metrics_row[10],
            ndcg_at_k=metrics_row[11],
        )

    judge_scores = [
        JudgeScoreRow(id=r[0], session_id=r[1], dimension=r[2], score=r[3],
                      rationale=r[4], judge_model=r[5], judge_prompt_hash=r[6])
        for r in judge_rows
    ]

    # Derive cluster_snapshot: clusters from the most recent clustered turn.
    cluster_snapshot: list[ClusterRow] = []
    for t in reversed(turns):
        if t.clusters:
            cluster_snapshot = t.clusters
            break

    log.debug(
        "get_session_full session=%s turns=%d clusters=%d",
        session_id, len(turns), len(cluster_rows),
    )
    return SessionRow(
        session_id=sess_row[0],
        run_id=sess_row[1],
        seed=sess_row[2],
        config_hash=sess_row[3],
        model_version=sess_row[4],
        status=sess_row[5],
        preference_profile=sess_row[6],
        created_at=sess_row[7],
        updated_at=sess_row[8],
        max_turns=sess_row[9],
        turns=turns,
        cluster_snapshot=cluster_snapshot,
        feedback=feedback,
        metrics=metrics,
        judge_scores=judge_scores,
    )
