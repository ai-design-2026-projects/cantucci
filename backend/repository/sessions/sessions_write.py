import json
import logging
import uuid
from decimal import Decimal
from typing import Any

from backend.repository.connection import transaction

log = logging.getLogger(__name__)


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
    """
    Insert a new session row and return its UUID.
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


def delete_session(session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """
    Delete a session row if it exists and is owned by user_id.

    Uses a single DELETE ... WHERE id = %s AND user_id = %s RETURNING id
    so authorization and deletion are atomic.

    The FK cascade defined in migrations/006_sessions.sql removes all child
    rows atomically: turns, clusters, cluster_assignments, oracle_feedback.
    The parent runs row is NOT deleted (sessions reference runs, not the
    other way around).
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


def mark_abandoned(session_id: uuid.UUID, reason: str) -> None:
    """
    Set session status to 'abandoned'.
    Called by the orchestrator when a hard limit (max_turns or max_recommendations)
    is reached.
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
    """
    Set session status to 'converged' and store the preference profile.
    Args:
        session_id: Session to mark as converged.
        preference_profile: Structured profile extracted from oracle feedback.
    """
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
