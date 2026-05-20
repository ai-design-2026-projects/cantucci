import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class Run(BaseModel):
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
