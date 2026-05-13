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


class SessionNotConverged(Exception):
    """Raised when the converged-cluster endpoint is called on an active session.

    The HTTP layer catches this and returns 409.

    Attributes:
        session_id: The session that has not yet converged.
        status:     The current status string (e.g. ``"active"``).
    """

    def __init__(self, session_id: UUID, status: str) -> None:
        self.session_id = session_id
        self.status = status
        super().__init__(
            f"Session {session_id} has not converged (status={status})"
        )


class MovieNotFound(Exception):
    """Raised when a movie_id is not present in the catalogue.

    The HTTP layer catches this and returns 404.

    Attributes:
        movie_id: The TMDB integer ID that was not found.
    """

    def __init__(self, movie_id: int) -> None:
        self.movie_id = movie_id
        super().__init__(f"Movie {movie_id} not found in catalogue")
