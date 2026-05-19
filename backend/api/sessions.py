"""
CRUD operations for session-runtime tables:
  sessions, turns, clusters, cluster_assignments, oracle_feedback.

The Orchestrator is the single caller of these functions. No other module
writes to these tables.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.api.db import transaction
from backend.api.types import ClusterAssignment, ClusterRow, ClusterSpecification

log = logging.getLogger(__name__)


@dataclass
class SessionListRow:
    """Lightweight projection of a session row for history listings.

    Attributes:
        session_id:         Session UUID.
        run_id:             UUID of the parent run.
        seed:               Per-session RNG seed.
        config_hash:        SHA-256 prefix of the YAML config snapshot.
        model_version:      LLM model identifier used for this session.
        status:             Lifecycle state (active | converged | abandoned).
        created_at:         UTC timestamp of session creation.
        updated_at:         UTC timestamp of the last state change.
        turn_count:         Number of completed turns in this session.
        first_user_message: Text of the first oracle message, or None for
                            sessions with no turns yet.
        cluster_snapshot:   Current cluster state (latest clustered turn's
                            clusters). Empty list when no clustered turn yet.
    """

    session_id: uuid.UUID
    run_id: uuid.UUID
    seed: int
    config_hash: str
    model_version: str
    status: str
    created_at: datetime
    updated_at: datetime
    turn_count: int
    first_user_message: str | None
    cluster_snapshot: list[ClusterRow] = field(default_factory=list)


def list_sessions_by_user(user_id: uuid.UUID) -> list[SessionListRow]:
    """Return all sessions owned by user_id, ordered newest-first by updated_at.

    Sessions with user_id = NULL (anonymous) are never returned.
    turn_count is computed via LEFT JOIN in a single round-trip. cluster_snapshot
    is populated with the clusters from the latest clustered turn, fetched in
    one additional SELECT for the batch of returned sessions.

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

    assignments_by_cluster: dict[uuid.UUID, list[ClusterAssignment]] = {}
    for r in assignment_rows:
        assignments_by_cluster.setdefault(r[0], []).append(
            ClusterAssignment(movie_id=r[1], score=r[2], excluded=r[3])
        )

    clusters_by_session: dict[uuid.UUID, list[ClusterRow]] = {}
    for r in cluster_rows:
        clusters_by_session.setdefault(r[1], []).append(
            ClusterRow(
                id=r[0], name=r[2], description=r[3], level=r[4],
                parent_cluster_id=r[5],
                assignments=assignments_by_cluster.get(r[0], []),
            )
        )

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


def delete_session(session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Delete a session row if it exists and is owned by user_id.

    Uses a single DELETE ... WHERE id = %s AND user_id = %s RETURNING id
    so authorization and deletion are atomic. Returns False when the row
    does not exist OR is owned by a different user — the caller should not
    distinguish between these two cases (404 in both, to avoid disclosing
    session existence to unauthorized callers).

    The FK cascade defined in migrations/006_sessions.sql removes all child
    rows atomically: turns, clusters, cluster_assignments, oracle_feedback.
    The parent runs row is NOT deleted (sessions reference runs, not the
    other way around).

    Active-session race: if a turn is in flight when this delete commits,
    the in-flight turn's next DB write will raise ForeignKeyViolation. That
    exception propagates through the orchestrator's existing broad-except in
    routers/sessions.py:_turn_event_stream, surfacing as an ErrorEvent on
    the NDJSON stream for the in-flight client. No orphan rows result.

    Args:
        session_id: UUID of the session to delete.
        user_id:    UUID of the requesting user; must match sessions.user_id.

    Returns:
        True if the row was deleted, False if not found or not owned.
    """
    with transaction() as conn:
        row = conn.execute(
            "DELETE FROM sessions WHERE id = %s AND user_id = %s RETURNING id",
            (session_id, user_id),
        ).fetchone()

    deleted = row is not None
    if deleted:
        log.info("deleted session %s user=%s", session_id, user_id)
    else:
        log.debug(
            "delete_session no-op session=%s user=%s (not found or not owned)",
            session_id, user_id,
        )
    return deleted


def create_session(
    run_id: uuid.UUID,
    seed: int,
    config_hash: str,
    model_version: str,
    max_turns: int = 15,
    cost_limit_usd: Decimal | None = None,
    user_id: uuid.UUID | None = None,
    persona_id: str | None = None,
    ground_truth_id: str | None = None,
) -> uuid.UUID:
    """Insert a new session row and return its UUID.

    Args:
        run_id: Parent run UUID.
        seed: Per-session RNG seed.
        config_hash: SHA-256 hex of the YAML config snapshot.
        model_version: LLM model identifier.
        max_turns: Hard turn budget for this session.
        cost_limit_usd: Optional cost hard-stop (raises CostLimitExceeded when hit).
        user_id: Authenticated user who owns this session; None for anonymous.
        persona_id: Kebab-case slug of the eval persona; None for live sessions.
        ground_truth_id: Kebab-case slug of the eval ground truth; None for live sessions.

    Returns:
        UUID of the newly created session.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO sessions
                (run_id, seed, config_hash, model_version, max_turns,
                 cost_limit_usd, user_id, persona_id, ground_truth_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (run_id, seed, config_hash, model_version,
             max_turns, cost_limit_usd, user_id, persona_id, ground_truth_id),
        ).fetchone()

    session_id: uuid.UUID = row[0]
    log.info("created session %s run=%s", session_id, run_id)
    return session_id


def append_turn(
    session_id: uuid.UUID,
    turn_number: int,
    user_message: str,
    assistant_message: str | None,
    step_type: str | None,
    converged: bool,
    turn_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a turn row and bump sessions.updated_at atomically.

    Args:
        session_id:        Parent session UUID.
        turn_number:       1-based sequential index within the session.
        user_message:      Raw oracle utterance.
        assistant_message: System response (clusters + question / recommendation).
        step_type:         One of show | ask | stop.
        converged:         Whether this turn declared convergence.
        turn_id:           Pre-allocated UUID for log correlation. If None, the
                           DB generates one via DEFAULT gen_random_uuid().

    Returns:
        UUID of the newly created turn.
    """
    effective_id = turn_id if turn_id is not None else uuid.uuid4()
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO turns
                (id, session_id, turn_number, user_message, assistant_message,
                 step_type, converged)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (effective_id, session_id, turn_number, user_message,
             assistant_message, step_type, converged),
        ).fetchone()

        conn.execute(
            "UPDATE sessions SET updated_at = NOW() WHERE id = %s",
            (session_id,),
        )

    turn_id: uuid.UUID = row[0]
    log.debug(
        "appended turn %s session=%s turn_number=%d step=%s converged=%s",
        turn_id, session_id, turn_number, step_type, converged,
    )
    return turn_id


def update_turn(
    turn_id: uuid.UUID,
    assistant_message: str,
    step_type: str,
    converged: bool,
) -> None:
    """Update an existing turn row with its final reply fields.

    Used when the turn row must be inserted before cluster snapshots (to satisfy
    the FK on clusters.turn_id) but the reply is only known after agent calls.

    Args:
        turn_id:           UUID of the turn to update.
        assistant_message: Final reply text from the Orchestrator.
        step_type:         One of show | ask | stop.
        converged:         Whether this turn declared convergence.
    """
    with transaction() as conn:
        conn.execute(
            """
            UPDATE turns
            SET assistant_message = %s,
                step_type = %s,
                converged = %s
            WHERE id = %s
            """,
            (assistant_message, step_type, converged, turn_id),
        )
    log.debug("updated turn %s step=%s converged=%s", turn_id, step_type, converged)


def snapshot_clusters(
    session_id: uuid.UUID,
    turn_id: uuid.UUID,
    clusters: list[ClusterSpecification],
) -> list[uuid.UUID]:
    """Insert clusters + their assignment rows for a single turn snapshot.

    All inserts run inside one transaction so the snapshot is atomic: either
    all clusters are saved or none are.

    Args:
        session_id: Session this snapshot belongs to.
        turn_id: Turn this snapshot was captured after.
        clusters: List of ClusterSpec objects describing each cluster.

    Returns:
        List of UUIDs for the inserted cluster rows, in the same order as input.
    """
    cluster_ids: list[uuid.UUID] = []

    with transaction() as conn:
        for spec in clusters:
            row = conn.execute(
                """
                INSERT INTO clusters
                    (session_id, turn_id, parent_cluster_id, name, description,
                     level, centroid)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    session_id, turn_id, spec.parent_cluster_id,
                    spec.name, spec.description, spec.level, spec.centroid,
                ),
            ).fetchone()

            cluster_id: uuid.UUID = row[0]
            cluster_ids.append(cluster_id)

            if spec.assignments:
                with conn.cursor() as cur:
                    cur.executemany(
                        """
                        INSERT INTO cluster_assignments
                            (cluster_id, movie_id, score, excluded)
                        VALUES (%s, %s, %s, %s)
                        """,
                        [
                            (cluster_id, movie_id, score, excluded)
                            for movie_id, score, excluded in spec.assignments
                        ],
                    )

    log.debug(
        "snapshot %d clusters for turn %s session=%s",
        len(clusters), turn_id, session_id,
    )
    return cluster_ids


def write_feedback(
    session_id: uuid.UUID,
    turn_id: uuid.UUID,
    feedback_level: str,
    feedback_type: str,
    content: str,
    target_id: str | None = None,
) -> uuid.UUID:
    """Append an oracle_feedback row. This table is append-only; never update.

    Args:
        session_id: Session UUID.
        turn_id: Turn UUID.
        feedback_level: One of global | cluster | point | instructional.
        feedback_type: One of accept | reject | split | merge | resolve_drift | constraint.
        content: Raw oracle utterance or parsed rule text.
        target_id: Cluster UUID or TMDB movie ID as string (nullable).

    Returns:
        UUID of the new feedback row.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO oracle_feedback
                (session_id, turn_id, feedback_level, feedback_type,
                 target_id, content)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (session_id, turn_id, feedback_level, feedback_type,
             target_id, content),
        ).fetchone()

    feedback_id: uuid.UUID = row[0]
    log.debug(
        "feedback %s level=%s type=%s session=%s",
        feedback_id, feedback_level, feedback_type, session_id,
    )
    return feedback_id


def mark_abandoned(session_id: uuid.UUID, reason: str) -> None:
    """Set session status to 'abandoned'.

    Called by the orchestrator when a hard limit (max_turns or max_recommendations)
    is reached. The ``reason`` is logged here for auditability but not persisted to
    the DB — it also lives in the terminating turn's assistant_message and log record.

    Args:
        session_id: Session to abandon.
        reason:     One-line description of the limit that was hit.
    """
    with transaction() as conn:
        conn.execute(
            "UPDATE sessions SET status = 'abandoned', updated_at = NOW() WHERE id = %s",
            (session_id,),
        )
    log.info(
        "session marked abandoned",
        extra={"session_id": str(session_id), "reason": reason},
    )


def mark_converged(
    session_id: uuid.UUID,
    preference_profile: dict[str, Any],
) -> None:
    """Set session status to 'converged' and store the preference profile.

    Args:
        session_id: Session to mark as converged.
        preference_profile: Structured profile extracted from oracle feedback.
    """
    import json

    with transaction() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status = 'converged',
                preference_profile = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            """,
            (json.dumps(preference_profile), session_id),
        )
    log.info("session %s marked converged", session_id)


def update_preference_profile(
    session_id: uuid.UUID,
    preference_profile: dict[str, Any],
) -> None:
    """Overwrite sessions.preference_profile with the latest extracted profile.

    Called at the end of every turn by the orchestrator, after the Profile
    Agent has returned an updated profile. The prior value is discarded.

    Args:
        session_id:         Session to update.
        preference_profile: Fresh structured profile dict from the Profile Agent.
    """
    import json

    with transaction() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET preference_profile = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            """,
            (json.dumps(preference_profile), session_id),
        )
    log.debug("preference_profile updated for session %s", session_id)
