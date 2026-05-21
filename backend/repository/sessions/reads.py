import logging
import uuid
from typing import Any

from backend.cluster.domain import ClusterAssignment
from backend.profile.types import UserProfile
from backend.repository.connection import transaction
from backend.repository.eval.types import JudgeScoreRow, SessionMetricsRow
from backend.repository.sessions.types import (
    ClusterRow,
    FeedbackRow,
    SessionListRow,
    SessionRow,
    TurnRow,
)

log = logging.getLogger(__name__)


def _hydrate_clusters(
    cluster_rows: list[Any],
    assignment_rows: list[Any],
) -> dict[uuid.UUID, list[ClusterRow]]:
    """
    Build a keyed dict of ClusterRow lists from raw DB rows.
    Args:
        cluster_rows:    Rows of (id, key_id, name, description, level,
                         parent_cluster_id) where key_id is the grouping key
                         (session_id for list queries, turn_id for full reads).
        assignment_rows: Rows of (cluster_id, movie_id, score, excluded).
    Returns:
        Dict mapping key_id → list of ClusterRow with assignments populated.
    """
    assignments_by_cluster: dict[uuid.UUID, list[ClusterAssignment]] = {}
    for r in assignment_rows:
        assignments_by_cluster.setdefault(r[0], []).append(
            ClusterAssignment(movie_id=r[1], score=r[2], excluded=r[3])
        )

    clusters_by_key: dict[uuid.UUID, list[ClusterRow]] = {}
    for r in cluster_rows:
        clusters_by_key.setdefault(r[1], []).append(
            ClusterRow(
                id=r[0], name=r[2], description=r[3], level=r[4],
                parent_cluster_id=r[5],
                assignments=assignments_by_cluster.get(r[0], []),
            )
        )

    return clusters_by_key


def list_sessions_by_user(user_id: uuid.UUID) -> list[SessionListRow]:
    """
    Return all sessions owned by user_id, ordered newest-first by updated_at.
    Args:
        user_id: UUID of the authenticated user.
    Returns:
        List of SessionListRow, ordered by updated_at DESC.
    """
    with transaction() as conn:
        session_rows = conn.execute(
            """
            SELECT s.id, s.run_id, s.seed, s.config_hash, s.model_version,
                   s.status, s.created_at, s.updated_at, COUNT(t.id),
                   (SELECT user_message FROM turns
                    WHERE session_id = s.id
                    ORDER BY turn_number ASC
                    LIMIT 1) AS first_user_message
            FROM sessions s
            LEFT JOIN turns t ON t.session_id = s.id
            WHERE s.user_id = %s
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            """,
            (user_id,),
        ).fetchall()

        if not session_rows:
            return []

        session_ids = [r[0] for r in session_rows]

        cluster_rows = conn.execute(
            """
            SELECT c.id, c.session_id, c.name, c.description, c.level,
                   c.parent_cluster_id
            FROM clusters c
            WHERE c.turn_id IN (
                SELECT DISTINCT ON (session_id) id
                FROM turns
                WHERE session_id = ANY(%s) AND id IN (
                    SELECT DISTINCT turn_id FROM clusters
                )
                ORDER BY session_id, turn_number DESC
            )
            ORDER BY c.session_id, c.level, c.name
            """,
            (session_ids,),
        ).fetchall()

        cluster_ids = [r[0] for r in cluster_rows]
        assignment_rows: list[Any] = []
        if cluster_ids:
            assignment_rows = conn.execute(
                """
                SELECT cluster_id, movie_id, score, excluded
                FROM cluster_assignments
                WHERE cluster_id = ANY(%s)
                """,
                (cluster_ids,),
            ).fetchall()

    clusters_by_session = _hydrate_clusters(cluster_rows, assignment_rows)

    return [
        SessionListRow(
            session_id=r[0],
            run_id=r[1],
            seed=r[2],
            config_hash=r[3],
            model_version=r[4],
            status=r[5],
            created_at=r[6],
            updated_at=r[7],
            turn_count=r[8],
            first_user_message=r[9],
            cluster_snapshot=clusters_by_session.get(r[0], []),
        )
        for r in session_rows
    ]


def get_session_full(session_id: uuid.UUID) -> SessionRow:
    """
    Retrieve from the DB the complete state of a session.
    Includes all turns, clusters, assignments, oracle feedback, and metrics.
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

        if sess_row is None:
            raise ValueError(f"session {session_id} not found")

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

        feedback_rows = conn.execute(
            """
            SELECT id, turn_id, feedback_level, feedback_type, target_id, content
            FROM oracle_feedback
            WHERE session_id = %s
            ORDER BY created_at
            """,
            (session_id,),
        ).fetchall()

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

        judge_rows = conn.execute(
            """
            SELECT id, session_id, dimension, score, rationale, judge_model, judge_prompt_hash
            FROM judge_scores
            WHERE session_id = %s
            ORDER BY created_at
            """,
            (session_id,),
        ).fetchall()

    clusters_by_turn = _hydrate_clusters(cluster_rows, assignment_rows)

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

    cluster_snapshot: list[ClusterRow] = []
    for t in reversed(turns):
        if t.clusters:
            cluster_snapshot = t.clusters
            break

    log.debug(
        "get_session_full session=%s turns=%d clusters=%d",
        session_id, len(turns), len(cluster_rows),
    )
    raw_profile = sess_row[6]
    return SessionRow(
        session_id=sess_row[0],
        run_id=sess_row[1],
        seed=sess_row[2],
        config_hash=sess_row[3],
        model_version=sess_row[4],
        status=sess_row[5],
        preference_profile=UserProfile.model_validate(raw_profile) if raw_profile is not None else None,
        created_at=sess_row[7],
        updated_at=sess_row[8],
        max_turns=sess_row[9],
        turns=turns,
        cluster_snapshot=cluster_snapshot,
        feedback=feedback,
        metrics=metrics,
        judge_scores=judge_scores,
    )
