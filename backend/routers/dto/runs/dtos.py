from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

from backend.routers.dto.eval.dtos import MetricBundleDto


class RunSummaryDto(BaseModel):
    """Lightweight run summary for the run listing endpoint.

    Attributes:
        id:          Run UUID.
        name:        Human-readable run label.
        condition:   Experimental condition.
        status:      Lifecycle status (running | completed | aborted).
        started_at:  UTC timestamp of run creation.
        ended_at:    UTC timestamp of finalization, or None if still running.
        n_sessions:  Total number of sessions in this run.
    """

    id: UUID
    name: str
    condition: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    n_sessions: int


class RunDetailDto(BaseModel):
    """Full run metadata with overall aggregate metrics.

    Attributes:
        id:            Run UUID.
        name:          Human-readable run label.
        condition:     Experimental condition.
        config_hash:   SHA-256 prefix of the YAML config snapshot.
        seed:          RNG seed shared across all sessions.
        model_version: LLM model identifier.
        status:        Lifecycle status.
        notes:         Optional free-text annotation.
        started_at:    UTC timestamp of run creation.
        ended_at:      UTC timestamp of finalization, or None.
        n_sessions:    Total number of sessions in this run.
        aggregate:     Overall per-metric CIs across all sessions.
    """

    id: UUID
    name: str
    condition: str
    config_hash: str
    seed: int
    model_version: str
    status: str
    notes: str | None
    started_at: datetime | None
    ended_at: datetime | None
    n_sessions: int
    aggregate: MetricBundleDto
