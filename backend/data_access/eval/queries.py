import json
import logging
import uuid
from typing import Any

from backend.data_access.connection import transaction
from backend.data_access.eval.types import (
    ConversationMetricsRow,
    EvalSessionRow,
    GroundTruthRow,
    JudgeScoreRow,
    PersonaRow,
    RunAggregateSessionRow,
    RunRow,
    TurnIntentRow,
)

log = logging.getLogger(__name__)


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


def get_run_by_name(name: str) -> RunRow | None:
    """Fetch the most recent run matching the given name.

    If multiple runs share the same name (names are not unique), the one with
    the latest ``started_at`` is returned.

    Args:
        name: Human-readable run label to look up.

    Returns:
        ``RunRow`` if a matching run exists, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT run_id, config_hash, config_snapshot, seed, started_at,
                   name, condition, model_version, ended_at, status, notes
            FROM runs WHERE name = %s ORDER BY started_at DESC LIMIT 1
            """,
            (name,),
        ).fetchone()
    return RunRow.from_row(row) if row else None


def count_runs_by_name(name: str) -> int:
    """Return the number of runs with the given name.

    Args:
        name: Human-readable run label to count.

    Returns:
        Number of matching runs.
    """
    with transaction() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM runs WHERE name = %s", (name,)).fetchone()
    return int(row["n"])


def list_runs(limit: int = 50, offset: int = 0) -> list[RunRow]:
    """Return runs ordered by creation time descending.

    Args:
        limit:  Maximum rows to return.
        offset: Pagination offset.

    Returns:
        List of ``RunRow``.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT run_id, config_hash, config_snapshot, seed, started_at,
                   name, condition, model_version, ended_at, status, notes
            FROM runs ORDER BY started_at DESC LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ).fetchall()
    return [RunRow.from_row(r) for r in rows]


def create_persona(
    slug: str,
    verbosity: str = "medium",
    patience: float = 0.5,
    definition: dict[str, Any] | None = None,
) -> uuid.UUID:
    """Insert a new persona row and return its UUID.

    Personas are write-once; changing behaviour requires a new slug.

    Args:
        slug:       Unique persona identifier.
        verbosity:  Reply-length dial (terse | medium | verbose).
        patience:   Willingness to continue after system misbehaviour [0, 1].
        definition: Extra JSONB fields.

    Returns:
        UUID of the newly created persona.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO personas (slug, verbosity, patience, definition)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (slug, verbosity, patience, json.dumps(definition or {})),
        ).fetchone()
    persona_id: uuid.UUID = row["id"]
    log.info("persona_created", extra={"persona_id": str(persona_id), "slug": slug})
    return persona_id


def get_persona_by_id(persona_id: uuid.UUID) -> PersonaRow | None:
    """Fetch a persona by its UUID.

    Args:
        persona_id: Persona UUID.

    Returns:
        ``PersonaRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, slug, verbosity, patience, definition, created_at FROM personas WHERE id = %s",
            (persona_id,),
        ).fetchone()
    return PersonaRow.from_row(row) if row else None


def get_persona_by_slug(slug: str) -> PersonaRow | None:
    """Fetch a persona by its slug.

    Args:
        slug: Unique persona identifier.

    Returns:
        ``PersonaRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, slug, verbosity, patience, definition, created_at FROM personas WHERE slug = %s",
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
            "SELECT id, slug, verbosity, patience, definition, created_at FROM personas ORDER BY created_at ASC",
        ).fetchall()
    return [PersonaRow.from_row(r) for r in rows]


def create_ground_truth(
    slug: str,
    intent_description: str,
    operations: list[dict[str, str]],
    prompt_hash: str,
    *,
    version: int = 1,
    seed_movie_ids: list[int] | None = None,
) -> uuid.UUID:
    """Insert a new ground truth row and return its UUID.

    Args:
        slug:              Unique identifier string.
        intent_description: Neutral intent description shown to the oracle.
        operations:        Ordered list of {op, concept} dicts.
        prompt_hash:       SHA-256 hex of the GT builder prompts.
        version:           Schema version for replay compatibility.
        seed_movie_ids:    Movie IDs used by the builder for audit, or None.

    Returns:
        UUID of the newly created ground truth.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO ground_truths (slug, version, intent_description, operations, seed_movie_ids, prompt_hash)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                slug,
                version,
                intent_description,
                json.dumps(operations),
                json.dumps(seed_movie_ids) if seed_movie_ids is not None else None,
                prompt_hash,
            ),
        ).fetchone()
    gt_id: uuid.UUID = row["id"]
    log.info("ground_truth_created", extra={"ground_truth_id": str(gt_id), "slug": slug})
    return gt_id


def get_ground_truth_by_id(ground_truth_id: uuid.UUID) -> GroundTruthRow | None:
    """Fetch a ground truth by its UUID.

    Args:
        ground_truth_id: Ground truth UUID.

    Returns:
        ``GroundTruthRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT id, slug, version, intent_description, operations, seed_movie_ids, prompt_hash, created_at
            FROM ground_truths WHERE id = %s
            """,
            (ground_truth_id,),
        ).fetchone()
    return GroundTruthRow.from_row(row) if row else None


def get_ground_truth_by_slug(slug: str) -> GroundTruthRow | None:
    """Fetch a ground truth by its slug.

    Args:
        slug: Unique ground truth identifier.

    Returns:
        ``GroundTruthRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT id, slug, version, intent_description, operations, seed_movie_ids, prompt_hash, created_at
            FROM ground_truths WHERE slug = %s
            """,
            (slug,),
        ).fetchone()
    return GroundTruthRow.from_row(row) if row else None


def list_ground_truths() -> list[GroundTruthRow]:
    """Return all ground truths ordered by creation time.

    Returns:
        List of ``GroundTruthRow`` ordered by ``created_at`` ascending.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, slug, version, intent_description, operations, seed_movie_ids, prompt_hash, created_at
            FROM ground_truths ORDER BY created_at ASC
            """,
        ).fetchall()
    return [GroundTruthRow.from_row(r) for r in rows]


def create_eval_session(
    run_id: uuid.UUID,
    conversation_id: uuid.UUID,
    seed: int,
    condition: str = "conversational",
    persona_id: uuid.UUID | None = None,
    ground_truth_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a new eval session row linking a conversation to a run.

    Args:
        run_id:          Parent run UUID.
        conversation_id: Linked conversation UUID.
        seed:            Per-session RNG seed.
        condition:       Experimental condition.
        persona_id:      Oracle persona UUID, or None for human sessions.
        ground_truth_id: Ground truth UUID, or None for human sessions.

    Returns:
        UUID of the newly created eval session.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO eval_sessions (run_id, conversation_id, persona_id, ground_truth_id, seed, condition)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (run_id, conversation_id, persona_id, ground_truth_id, seed, condition),
        ).fetchone()
    session_id: uuid.UUID = row["id"]
    log.info("eval_session_created", extra={"eval_session_id": str(session_id), "conversation_id": str(conversation_id)})
    return session_id


def set_eval_session_termination(
    eval_session_id: uuid.UUID,
    *,
    status: str,
    rationale: str | None,
    oracle_rating: int | None,
) -> None:
    """Record the oracle's termination decision on an eval session.

    Args:
        eval_session_id: Eval session UUID to update.
        status:          Terminal status (finished_trajectory | finished_misbehaviour | finished_budget).
        rationale:       Free-text rationale from oracle.
        oracle_rating:   1–5 self-rating from oracle, or None for human/no-rating.
    """
    with transaction() as conn:
        conn.execute(
            "UPDATE eval_sessions SET status = %s, termination_rationale = %s, oracle_rating = %s WHERE id = %s",
            (status, rationale, oracle_rating, eval_session_id),
        )
    log.info("eval_session_terminated", extra={"eval_session_id": str(eval_session_id), "status": status})


def get_eval_session_by_conversation(conversation_id: uuid.UUID) -> EvalSessionRow | None:
    """Fetch an eval session by its linked conversation UUID.

    Args:
        conversation_id: Linked conversation UUID.

    Returns:
        ``EvalSessionRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT id, run_id, conversation_id, persona_id, ground_truth_id,
                   seed, condition, status, termination_rationale, oracle_rating, created_at
            FROM eval_sessions WHERE conversation_id = %s
            """,
            (conversation_id,),
        ).fetchone()
    return EvalSessionRow.from_row(row) if row else None


def get_eval_session(eval_session_id: uuid.UUID) -> EvalSessionRow | None:
    """Fetch an eval session by its UUID.

    Args:
        eval_session_id: Eval session UUID.

    Returns:
        ``EvalSessionRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT id, run_id, conversation_id, persona_id, ground_truth_id,
                   seed, condition, status, termination_rationale, oracle_rating, created_at
            FROM eval_sessions WHERE id = %s
            """,
            (eval_session_id,),
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
            """
            SELECT id, run_id, conversation_id, persona_id, ground_truth_id,
                   seed, condition, status, termination_rationale, oracle_rating, created_at
            FROM eval_sessions WHERE run_id = %s ORDER BY created_at ASC
            """,
            (run_id,),
        ).fetchall()
    return [EvalSessionRow.from_row(r) for r in rows]


def insert_turn_intent(
    conversation_id: uuid.UUID,
    turn_number: int,
    mode: str,
    confidence: float,
    raw_intent: dict[str, Any],
    *,
    concept: str | None = None,
    target_cluster_id: uuid.UUID | None = None,
    clarifier_fired: bool = False,
) -> uuid.UUID:
    """Persist one intent action row for a coordinator turn.

    Compound turns with multiple actions produce multiple rows (same turn_number,
    different mode). The UNIQUE constraint on (conversation_id, turn_number, mode)
    prevents duplicate inserts.

    Args:
        conversation_id:   Parent conversation UUID.
        turn_number:       1-based oracle turn ordinal.
        mode:              NavigationMode or DialogueMode value string.
        confidence:        Intent confidence in [0, 1].
        raw_intent:        Full raw intent dict for audit.
        concept:           Semantic concept string, or None.
        target_cluster_id: Target cluster UUID, or None.
        clarifier_fired:   True if the clarifier gate fired this turn.

    Returns:
        UUID of the inserted row.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO turn_intents (
                conversation_id, turn_number, mode, concept,
                target_cluster_id, confidence, clarifier_fired, raw_intent
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (conversation_id, turn_number, mode) DO NOTHING
            RETURNING id
            """,
            (
                conversation_id, turn_number, mode, concept,
                target_cluster_id, confidence, clarifier_fired,
                json.dumps(raw_intent),
            ),
        ).fetchone()
    if row is None:
        log.debug("turn_intent_duplicate_skipped", extra={"conversation_id": str(conversation_id), "turn_number": turn_number, "mode": mode})
        return uuid.UUID(int=0)
    return row["id"]


def list_turn_intents(conversation_id: uuid.UUID) -> list[TurnIntentRow]:
    """Return all turn intent rows for a conversation, ordered by turn then created.

    Args:
        conversation_id: Parent conversation UUID.

    Returns:
        List of ``TurnIntentRow`` ordered by (turn_number, created_at) ascending.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, conversation_id, turn_number, mode, concept,
                   target_cluster_id, confidence, clarifier_fired, raw_intent, created_at
            FROM turn_intents WHERE conversation_id = %s
            ORDER BY turn_number ASC, created_at ASC
            """,
            (conversation_id,),
        ).fetchall()
    return [TurnIntentRow.from_row(r) for r in rows]


def upsert_conversation_metrics(
    conversation_id: uuid.UUID,
    final_num_clusters: int | None,
    operation_recall: float | None,
    clarifier_trigger_rate: float | None,
    num_turns: int,
    num_operations: int,
    total_cost_usd: float,
) -> None:
    """Insert or overwrite deterministic eval metrics for a conversation.

    Safe to call multiple times; later calls overwrite earlier ones (PK upsert).

    Args:
        conversation_id:       Parent conversation UUID.
        final_num_clusters:    Number of clusters in the final snapshot.
        operation_recall:      Fraction of GT operations executed, or None.
        clarifier_trigger_rate: Fraction of turns with clarifier gate fired.
        num_turns:             Total oracle turns.
        num_operations:        Total navigation operations executed.
        total_cost_usd:        Accumulated LLM cost.
    """
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO conversation_metrics (
                conversation_id, final_num_clusters, operation_recall, clarifier_trigger_rate,
                num_turns, num_operations, total_cost_usd, computed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (conversation_id) DO UPDATE SET
                final_num_clusters     = EXCLUDED.final_num_clusters,
                operation_recall       = EXCLUDED.operation_recall,
                clarifier_trigger_rate = EXCLUDED.clarifier_trigger_rate,
                num_turns              = EXCLUDED.num_turns,
                num_operations         = EXCLUDED.num_operations,
                total_cost_usd         = EXCLUDED.total_cost_usd,
                computed_at            = NOW()
            """,
            (
                conversation_id, final_num_clusters, operation_recall, clarifier_trigger_rate,
                num_turns, num_operations, total_cost_usd,
            ),
        )
    log.info("conversation_metrics_upserted", extra={"conversation_id": str(conversation_id)})


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
            SELECT conversation_id, final_num_clusters, operation_recall, clarifier_trigger_rate,
                   num_turns, num_operations, total_cost_usd, computed_at
            FROM conversation_metrics WHERE conversation_id = %s
            """,
            (conversation_id,),
        ).fetchone()
    return ConversationMetricsRow.from_row(row) if row else None


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


def get_run_aggregate(run_id: uuid.UUID) -> tuple[RunRow | None, list[RunAggregateSessionRow]]:
    """Return a run and all its sessions with metrics and latest judge scores in two queries.

    First fetches the run row; if it exists, one SQL round-trip joins eval_sessions,
    conversation_metrics, and the latest judge score per (conversation, dimension).

    Args:
        run_id: Target run UUID.

    Returns:
        A tuple of (RunRow | None, list[RunAggregateSessionRow]). RunRow is None when
        the run does not exist; the session list is empty in that case.
    """
    run = get_run(run_id)
    if run is None:
        return None, []

    with transaction() as conn:
        rows = conn.execute(
            """
            WITH latest_judge AS (
                SELECT DISTINCT ON (js.conversation_id, js.dimension)
                    js.id, js.conversation_id, js.dimension, js.score, js.rationale,
                    js.judge_model, js.judge_prompt_hash, js.created_at
                FROM judge_scores js
                WHERE js.conversation_id IN (
                    SELECT conversation_id FROM eval_sessions WHERE run_id = %s
                )
                ORDER BY js.conversation_id, js.dimension, js.created_at DESC
            ),
            session_judge AS (
                SELECT
                    conversation_id,
                    jsonb_agg(jsonb_build_object(
                        'id',               id::text,
                        'dimension',        dimension,
                        'score',            score,
                        'rationale',        rationale,
                        'judge_model',      judge_model,
                        'judge_prompt_hash', judge_prompt_hash,
                        'created_at',       created_at::text
                    )) AS judge_scores
                FROM latest_judge
                GROUP BY conversation_id
            ),
            session_confidence AS (
                SELECT conversation_id, AVG(confidence) AS mean_confidence
                FROM turn_intents
                WHERE conversation_id IN (
                    SELECT conversation_id FROM eval_sessions WHERE run_id = %s
                )
                GROUP BY conversation_id
            )
            SELECT
                es.id, es.run_id, es.conversation_id, es.persona_id, es.ground_truth_id,
                es.seed, es.condition, es.status, es.termination_rationale, es.oracle_rating,
                es.created_at,
                cm.final_num_clusters, cm.operation_recall, cm.clarifier_trigger_rate,
                cm.num_turns, cm.num_operations, cm.total_cost_usd,
                cm.computed_at AS metrics_computed_at,
                COALESCE(sj.judge_scores, '[]'::jsonb) AS judge_scores,
                p.slug AS persona_slug,
                p.verbosity AS persona_verbosity,
                p.patience AS persona_patience,
                sc.mean_confidence,
                gt.slug AS ground_truth_slug
            FROM eval_sessions es
            LEFT JOIN conversation_metrics cm ON cm.conversation_id = es.conversation_id
            LEFT JOIN session_judge sj ON sj.conversation_id = es.conversation_id
            LEFT JOIN personas p ON p.id = es.persona_id
            LEFT JOIN session_confidence sc ON sc.conversation_id = es.conversation_id
            LEFT JOIN ground_truths gt ON gt.id = es.ground_truth_id
            WHERE es.run_id = %s
            ORDER BY es.created_at ASC
            """,
            (run_id, run_id, run_id),
        ).fetchall()

    return run, [RunAggregateSessionRow.from_row(r) for r in rows]
