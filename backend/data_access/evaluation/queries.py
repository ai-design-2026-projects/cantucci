import json
import logging
import uuid
from typing import Any

from backend.data_access.connection import transaction
from backend.data_access.evaluation.types import (
    ConversationMetricsRow,
    EvalSessionRow,
    GroundTruthRow,
    JudgeScoreRow,
    PersonaRow,
    RunRow,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def create_run(
    config_hash: str,
    config_snapshot: dict[str, Any],
    seed: int,
    name: str | None = None,
    condition: str = "conversational",
    model_version: str | None = None,
    notes: str | None = None,
) -> uuid.UUID:
    """Insert a new eval run row and return its UUID.

    Args:
        config_hash:     SHA-256 8-char prefix of the active YAML config.
        config_snapshot: Full YAML config dict.
        seed:            RNG seed for the run.
        name:            Human-readable run label.
        condition:       Experimental condition (conversational | baseline | human).
        model_version:   LLM model identifier string.
        notes:           Free-text notes.

    Returns:
        UUID of the newly created run.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO runs (config_hash, config_snapshot, seed, name, condition, model_version, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING run_id
            """,
            (config_hash, json.dumps(config_snapshot), seed, name, condition, model_version, notes),
        ).fetchone()
    run_id: uuid.UUID = row["run_id"]
    log.info("run_created", extra={"run_id": str(run_id), "condition": condition})
    return run_id


def set_run_status(run_id: uuid.UUID, status: str) -> None:
    """Update the status of a run (running | completed | aborted).

    Args:
        run_id: Run UUID to update.
        status: New status string.
    """
    with transaction() as conn:
        conn.execute(
            "UPDATE runs SET status = %s, ended_at = CASE WHEN %s != 'running' THEN NOW() ELSE ended_at END WHERE run_id = %s",
            (status, status, run_id),
        )
    log.info("run_status_updated", extra={"run_id": str(run_id), "status": status})


def get_run(run_id: uuid.UUID) -> RunRow | None:
    """Fetch a run row by UUID.

    Args:
        run_id: Run UUID to look up.

    Returns:
        ``RunRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT run_id, config_hash, config_snapshot, seed, started_at,
                   name, condition, model_version, ended_at, status, notes
            FROM runs WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()
    return RunRow.from_row(row) if row else None


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

def create_persona(
    slug: str,
    verbosity: str = "medium",
    decisiveness: float = 0.5,
    drift_probability: float = 0.0,
    contradiction_rate: float = 0.0,
    definition: dict[str, Any] | None = None,
) -> uuid.UUID:
    """Insert a new persona row and return its UUID.

    Personas are write-once; changing behaviour requires a new slug.

    Args:
        slug:               Unique persona identifier.
        verbosity:          Reply-length dial (terse | medium | verbose).
        decisiveness:       Minimum-turn acceptance probability [0, 1].
        drift_probability:  Per-turn tangent injection probability [0, 1].
        contradiction_rate: Per-turn contradiction injection probability [0, 1].
        definition:         Extra JSONB fields.

    Returns:
        UUID of the newly created persona.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO personas (slug, verbosity, decisiveness, drift_probability, contradiction_rate, definition)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (slug, verbosity, decisiveness, drift_probability, contradiction_rate, json.dumps(definition or {})),
        ).fetchone()
    persona_id: uuid.UUID = row["id"]
    log.info("persona_created", extra={"persona_id": str(persona_id), "slug": slug})
    return persona_id


def get_persona_by_slug(slug: str) -> PersonaRow | None:
    """Fetch a persona by its slug.

    Args:
        slug: Unique persona identifier.

    Returns:
        ``PersonaRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, slug, verbosity, decisiveness, drift_probability, contradiction_rate, definition, created_at FROM personas WHERE slug = %s",
            (slug,),
        ).fetchone()
    return PersonaRow.from_row(row) if row else None


def list_personas() -> list[PersonaRow]:
    """Return all personas ordered by creation time.

    Returns:
        List of ``PersonaRow`` ordered by ``created_at`` ascending.
    """
    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, slug, verbosity, decisiveness, drift_probability, contradiction_rate, definition, created_at FROM personas ORDER BY created_at ASC",
        ).fetchall()
    return [PersonaRow.from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Ground truths
# ---------------------------------------------------------------------------

def create_ground_truth(
    slug: str,
    description: str,
    seed_movie_ids: list[int],
    target_movie_ids: list[int],
    spec: dict[str, Any] | None = None,
) -> uuid.UUID:
    """Insert a new ground truth row and return its UUID.

    Args:
        slug:             Unique identifier string.
        description:      Neutral taste description shown to the oracle.
        seed_movie_ids:   Seed TMDB IDs used to expand the target set.
        target_movie_ids: Hidden expanded film set for spec-satisfaction scoring.
        spec:             Positive/negative criteria dict.

    Returns:
        UUID of the newly created ground truth.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO ground_truths (slug, description, seed_movie_ids, target_movie_ids, spec)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                slug,
                description,
                json.dumps(seed_movie_ids),
                json.dumps(target_movie_ids),
                json.dumps(spec or {}),
            ),
        ).fetchone()
    gt_id: uuid.UUID = row["id"]
    log.info("ground_truth_created", extra={"ground_truth_id": str(gt_id), "slug": slug})
    return gt_id


def get_ground_truth_by_slug(slug: str) -> GroundTruthRow | None:
    """Fetch a ground truth by its slug.

    Args:
        slug: Unique ground truth identifier.

    Returns:
        ``GroundTruthRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, slug, description, seed_movie_ids, target_movie_ids, spec, created_at FROM ground_truths WHERE slug = %s",
            (slug,),
        ).fetchone()
    return GroundTruthRow.from_row(row) if row else None


# ---------------------------------------------------------------------------
# Eval sessions
# ---------------------------------------------------------------------------

def create_eval_session(
    run_id: uuid.UUID,
    conversation_id: uuid.UUID,
    seed: int,
    persona_id: uuid.UUID | None = None,
    ground_truth_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a new eval session row linking a conversation to a run.

    Args:
        run_id:          Parent run UUID.
        conversation_id: Linked conversation UUID.
        seed:            Per-session RNG seed.
        persona_id:      Oracle persona UUID, or None for human sessions.
        ground_truth_id: Ground truth UUID, or None for human sessions.

    Returns:
        UUID of the newly created eval session.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO eval_sessions (run_id, conversation_id, persona_id, ground_truth_id, seed)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (run_id, conversation_id, persona_id, ground_truth_id, seed),
        ).fetchone()
    session_id: uuid.UUID = row["id"]
    log.info("eval_session_created", extra={"eval_session_id": str(session_id), "conversation_id": str(conversation_id)})
    return session_id


def set_eval_session_status(conversation_id: uuid.UUID, status: str) -> None:
    """Update the status of an eval session keyed by its conversation.

    Args:
        conversation_id: Linked conversation UUID.
        status:          New status (active | converged | abandoned).
    """
    with transaction() as conn:
        conn.execute(
            "UPDATE eval_sessions SET status = %s WHERE conversation_id = %s",
            (status, conversation_id),
        )
    log.info("eval_session_status_updated", extra={"conversation_id": str(conversation_id), "status": status})


def get_eval_session_by_conversation(conversation_id: uuid.UUID) -> EvalSessionRow | None:
    """Fetch an eval session by its linked conversation UUID.

    Args:
        conversation_id: Linked conversation UUID.

    Returns:
        ``EvalSessionRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, run_id, conversation_id, persona_id, ground_truth_id, seed, status, created_at FROM eval_sessions WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()
    return EvalSessionRow.from_row(row) if row else None


def list_eval_sessions_for_run(run_id: uuid.UUID) -> list[EvalSessionRow]:
    """Return all eval sessions for a run, ordered by creation time.

    Args:
        run_id: Parent run UUID.

    Returns:
        List of ``EvalSessionRow`` ordered by ``created_at`` ascending.
    """
    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, run_id, conversation_id, persona_id, ground_truth_id, seed, status, created_at FROM eval_sessions WHERE run_id = %s ORDER BY created_at ASC",
            (run_id,),
        ).fetchall()
    return [EvalSessionRow.from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Conversation metrics
# ---------------------------------------------------------------------------

def upsert_conversation_metrics(
    conversation_id: uuid.UUID,
    silhouette: float | None,
    mean_membership_prob: float | None,
    noise_fraction: float | None,
    final_num_clusters: int | None,
    spec_satisfaction_rate: float | None,
    converged: bool,
    num_turns: int,
    total_cost_usd: float,
    turns_to_convergence: int | None = None,
) -> None:
    """Insert or overwrite deterministic eval metrics for a conversation.

    Safe to call multiple times; later calls overwrite earlier ones (PK upsert).

    Args:
        conversation_id:       Parent conversation UUID.
        silhouette:            Silhouette score, or None when not computable.
        mean_membership_prob:  Mean argmax membership probability.
        noise_fraction:        Fraction of low-probability movies.
        final_num_clusters:    Number of clusters in the final snapshot.
        spec_satisfaction_rate: Hidden-spec satisfaction rate, or None.
        converged:             True if the oracle explicitly accepted.
        num_turns:             Total oracle turns.
        total_cost_usd:        Accumulated LLM cost.
        turns_to_convergence:  Turn index of acceptance, or None.
    """
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO conversation_metrics (
                conversation_id, silhouette, mean_membership_prob, noise_fraction,
                final_num_clusters, spec_satisfaction_rate, converged,
                turns_to_convergence, num_turns, total_cost_usd, computed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (conversation_id) DO UPDATE SET
                silhouette            = EXCLUDED.silhouette,
                mean_membership_prob  = EXCLUDED.mean_membership_prob,
                noise_fraction        = EXCLUDED.noise_fraction,
                final_num_clusters    = EXCLUDED.final_num_clusters,
                spec_satisfaction_rate = EXCLUDED.spec_satisfaction_rate,
                converged             = EXCLUDED.converged,
                turns_to_convergence  = EXCLUDED.turns_to_convergence,
                num_turns             = EXCLUDED.num_turns,
                total_cost_usd        = EXCLUDED.total_cost_usd,
                computed_at           = NOW()
            """,
            (
                conversation_id, silhouette, mean_membership_prob, noise_fraction,
                final_num_clusters, spec_satisfaction_rate, converged,
                turns_to_convergence, num_turns, total_cost_usd,
            ),
        )
    log.info("conversation_metrics_upserted", extra={"conversation_id": str(conversation_id), "converged": converged})


def get_conversation_metrics(conversation_id: uuid.UUID) -> ConversationMetricsRow | None:
    """Fetch deterministic eval metrics for a conversation.

    Args:
        conversation_id: Parent conversation UUID.

    Returns:
        ``ConversationMetricsRow`` if found, ``None`` if not yet computed.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT conversation_id, silhouette, mean_membership_prob, noise_fraction,
                   final_num_clusters, spec_satisfaction_rate, converged,
                   turns_to_convergence, num_turns, total_cost_usd, computed_at
            FROM conversation_metrics WHERE conversation_id = %s
            """,
            (conversation_id,),
        ).fetchone()
    return ConversationMetricsRow.from_row(row) if row else None


# ---------------------------------------------------------------------------
# Judge scores
# ---------------------------------------------------------------------------

def insert_judge_score(
    conversation_id: uuid.UUID,
    dimension: str,
    score: int,
    judge_model: str,
    judge_prompt_hash: str,
    rationale: str | None = None,
) -> uuid.UUID:
    """Append a judge score row for one dimension.

    The UNIQUE constraint on (conversation_id, dimension, judge_prompt_hash)
    prevents duplicates; callers should not insert the same dimension twice with
    the same prompt hash.

    Args:
        conversation_id:   Scored conversation UUID.
        dimension:         Judge dimension name.
        score:             Integer score in [1, 5].
        judge_model:       Model identifier string.
        judge_prompt_hash: SHA-256 hex of the rendered judge prompt.
        rationale:         One-sentence rationale from the judge.

    Returns:
        UUID of the newly inserted score row.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO judge_scores (conversation_id, dimension, score, rationale, judge_model, judge_prompt_hash)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (conversation_id, dimension, score, rationale, judge_model, judge_prompt_hash),
        ).fetchone()
    score_id: uuid.UUID = row["id"]
    log.debug("judge_score_inserted", extra={"conversation_id": str(conversation_id), "dimension": dimension, "score": score})
    return score_id


def get_judge_scores(conversation_id: uuid.UUID) -> list[JudgeScoreRow]:
    """Return all judge scores for a conversation, newest first.

    Args:
        conversation_id: Parent conversation UUID.

    Returns:
        List of ``JudgeScoreRow`` ordered by ``created_at`` descending.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, conversation_id, dimension, score, rationale, judge_model, judge_prompt_hash, created_at
            FROM judge_scores WHERE conversation_id = %s ORDER BY created_at DESC
            """,
            (conversation_id,),
        ).fetchall()
    return [JudgeScoreRow.from_row(r) for r in rows]
