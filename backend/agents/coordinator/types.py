import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CoordinatorResult:
    """Output of a single Coordinator.handle_message call.

    Attributes:
        reply_text:          Text to send back to the user.
        cluster_snapshot_id: UUID of the active cluster snapshot after this message.
        suggestion:          Optional follow-up suggestion from the suggester agent.
                             None on clarification paths, small_talk, explain, and reset.
    """

    reply_text: str
    cluster_snapshot_id: uuid.UUID
    suggestion: str | None = None


def sentinel_cluster_snapshot_id() -> uuid.UUID:
    """Return a zero UUID as a sentinel when no cluster snapshot exists yet."""
    return uuid.UUID("00000000-0000-0000-0000-000000000000")
