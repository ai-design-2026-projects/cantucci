import uuid
from dataclasses import dataclass


@dataclass
class CoordinatorResult:
    """Output of a single Coordinator.handle_message call.

    Attributes:
        reply_text:          Text to send back to the user.
        cluster_snapshot_id: UUID of the active cluster snapshot after this message.
    """
    reply_text: str
    cluster_snapshot_id: uuid.UUID
