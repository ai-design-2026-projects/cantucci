"""Domain exceptions raised by the orchestrator and caught by the HTTP layer."""

from uuid import UUID


class SessionNotFound(Exception):
    """Raised by the orchestrator when a session_id does not exist.

    The HTTP layer catches this and returns 404.

    Attributes:
        session_id: The UUID that was looked up and not found.
    """

    def __init__(self, session_id: UUID) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id} not found")
