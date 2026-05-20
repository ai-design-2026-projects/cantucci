import logging
import uuid

from backend.cluster.domain import ClusterSpecification
from backend.repository.connection import transaction

log = logging.getLogger(__name__)


def append_turn(
    session_id: uuid.UUID,
    turn_number: int,
    user_message: str,
    assistant_message: str | None,
    step_type: str | None,
    converged: bool,
    turn_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """
    Insert a turn row and bump sessions.updated_at atomically.
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

        # Update the session's updated_at to reflect the new turn.
        conn.execute(
            "UPDATE sessions SET updated_at = NOW() WHERE id = %s",
            (session_id,),
        )

    stored_turn_id: uuid.UUID = row[0]
    log.debug(
        "appended turn %s session=%s turn_number=%d step=%s converged=%s",
        stored_turn_id, session_id, turn_number, step_type, converged,
    )
    return stored_turn_id


def update_turn(
    turn_id: uuid.UUID,
    assistant_message: str,
    step_type: str,
    converged: bool,
) -> None:
    """
    Update an existing turn row with its final reply fields.
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
    """
    Insert clusters + their assignment rows for a single turn snapshot.
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
    """
    Append an oracle_feedback row. This table is append-only; never update.
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
