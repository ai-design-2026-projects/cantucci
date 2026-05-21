import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Run:
    """In-memory representation of a runs row."""
    id: uuid.UUID
    name: str
    condition: str
    config_hash: str
    config_snapshot: dict[str, Any]
    seed: int
    model_version: str
    status: str
    notes: str | None
    started_at: datetime | None = None
    ended_at: datetime | None = None
