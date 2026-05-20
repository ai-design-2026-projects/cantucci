import json
import logging
import uuid
from typing import Any, Literal

from backend.repository.connection import transaction
from backend.repository.runs.types import Run

log = logging.getLogger(__name__)


def create_run(
    name: str,
    condition: str,
    config_snapshot: dict[str, Any],
    config_hash: str,
    seed: int,
    model_version: str,
    notes: str | None = None,
) -> uuid.UUID:
    """
    Insert a new run row and return its UUID.
    Args:
        name: Human-readable label (e.g. "ablation-uncertainty-2024-05").
        condition: One of baseline | uncertainty | random | boundary | popularity
                   | component_test | human.
        config_snapshot: Full YAML config dict for this run (stored as JSONB).
        config_hash: SHA-256 prefix of the YAML config file (from
                     ``backend.settings.get_config_hash``). The replayability
                     contract requires this match the value used by sessions
                     and log records under the same config.
        seed: RNG seed shared across all sessions in this run.
        model_version: LLM model identifier (e.g. "claude-opus-4-7").
        notes: Optional free-text annotation.
    Returns:
        UUID of the newly created run.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO runs (name, condition, config_hash, config_snapshot,
                              seed, model_version, notes)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
            RETURNING id
            """,
            (name, condition, config_hash, json.dumps(config_snapshot),
             seed, model_version, notes),
        ).fetchone()

    run_id: uuid.UUID = row[0]
    log.info("created run %s condition=%s", run_id, condition)
    return run_id


def finalize_run(
    run_id: uuid.UUID,
    status: Literal["completed", "aborted"],
) -> None:
    """
    Set run status to completed or aborted and record ended_at.
    Args:
        run_id: UUID of the run to finalize.
        status: Terminal status value.
    """
    with transaction() as conn:
        conn.execute(
            """
            UPDATE runs
            SET status = %s, ended_at = NOW()
            WHERE id = %s
            """,
            (status, run_id),
        )
    log.info("finalized run %s status=%s", run_id, status)


def get_run(run_id: uuid.UUID) -> Run:
    """
    Fetch a run by UUID. Raises ValueError if not found.
    Args:
        run_id: UUID of the run.
    Returns:
        Run dataclass with all fields populated.
    Raises:
        ValueError: If the run does not exist.
    """
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT id, name, condition, config_hash, config_snapshot,
                   seed, model_version, status, notes, started_at, ended_at
            FROM runs
            WHERE id = %s
            """,
            (run_id,),
        ).fetchone()

    if row is None:
        raise ValueError(f"run {run_id} not found")

    return Run(
        id=row[0],
        name=row[1],
        condition=row[2],
        config_hash=row[3],
        config_snapshot=row[4],
        seed=row[5],
        model_version=row[6],
        status=row[7],
        notes=row[8],
        started_at=row[9],
        ended_at=row[10],
    )


def list_runs(
    condition: str | None = None,
    status: str | None = None,
) -> list[Run]:
    """
    List runs, optionally filtered by condition and/or status.
    Args:
        condition: Filter to this condition string (exact match).
        status: Filter to this status string (exact match).
    Returns:
        List of Run objects ordered by started_at descending.
    """
    clauses = []
    params: list[Any] = []

    if condition is not None:
        clauses.append("condition = %s")
        params.append(condition)
    if status is not None:
        clauses.append("status = %s")
        params.append(status)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    with transaction() as conn:
        rows = conn.execute(
            f"""
            SELECT id, name, condition, config_hash, config_snapshot,
                   seed, model_version, status, notes, started_at, ended_at
            FROM runs
            {where}
            ORDER BY started_at DESC
            """,
            params,
        ).fetchall()

    return [
        Run(
            id=r[0], name=r[1], condition=r[2], config_hash=r[3],
            config_snapshot=r[4], seed=r[5], model_version=r[6],
            status=r[7], notes=r[8], started_at=r[9], ended_at=r[10],
        )
        for r in rows
    ]
