from uuid import UUID


class DomainError(Exception):
    """Base for all application-domain failures.

    The ``@app.exception_handler(DomainError)`` in ``backend.app`` maps
    subclasses to HTTP responses using ``http_status``. Raise subclasses
    from any layer; the router need not catch them.
    """
    http_status: int = 500


class NotFoundError(DomainError):
    """Base for resource-not-found failures. Maps to HTTP 404."""
    http_status: int = 404


class ParseError(DomainError):
    """Base for parse / validation failures. Maps to HTTP 422."""
    http_status: int = 422


class AuthError(DomainError):
    """Base for authentication and authorisation failures. Maps to HTTP 401."""
    http_status: int = 401


class OperationalError(DomainError):
    """Base for operational / environmental failures. Maps to HTTP 500."""
    http_status: int = 500


class ConversationNotFound(NotFoundError):
    """Raised when a conversation_id does not exist in the DB.

    Attributes:
        conversation_id: The UUID that was looked up and not found.
    """

    def __init__(self, conversation_id: UUID) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"Conversation {conversation_id} not found")


class ClusterSnapshotNotFound(NotFoundError):
    """Raised when a cluster_snapshot_id does not exist in the DB.

    Attributes:
        cluster_snapshot_id: The UUID that was looked up and not found.
    """

    def __init__(self, cluster_snapshot_id: UUID) -> None:
        self.cluster_snapshot_id = cluster_snapshot_id
        super().__init__(f"Cluster snapshot {cluster_snapshot_id} not found")


class MovieNotFound(NotFoundError):
    """Raised when a movie_id is not present in the catalogue.

    Attributes:
        movie_id: The TMDB integer ID that was not found.
    """

    def __init__(self, movie_id: int) -> None:
        self.movie_id = movie_id
        super().__init__(f"Movie {movie_id} not found in catalogue")


class ConceptParseError(ParseError):
    """Raised when the concept agent cannot parse a user-supplied concept string.

    Attributes:
        raw: The raw concept string that could not be parsed.
    """

    def __init__(self, raw: str) -> None:
        self.raw = raw
        super().__init__(f"Could not parse concept: {raw!r}")


class ForbiddenError(DomainError):
    """Base for authorization failures (authenticated but not permitted). Maps to HTTP 403."""
    http_status: int = 403


class ConflictError(DomainError):
    """Base for conflict failures (state precondition not met). Maps to HTTP 409."""
    http_status: int = 409


class NotConversationOwner(ForbiddenError):
    """Raised when an authenticated user attempts to modify a conversation they do not own.

    Attributes:
        conversation_id: The conversation UUID that was accessed without permission.
    """

    def __init__(self, conversation_id: UUID) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"Not authorized to modify conversation {conversation_id}")


class SnapshotHasChildren(ConflictError):
    """Raised when a cluster snapshot cannot be deleted because child snapshots reference it.

    Attributes:
        cluster_snapshot_id: The snapshot UUID that still has children.
    """

    def __init__(self, cluster_snapshot_id: UUID) -> None:
        self.cluster_snapshot_id = cluster_snapshot_id
        super().__init__(f"Cluster snapshot {cluster_snapshot_id} has child snapshots and cannot be deleted")


class TokenExpired(AuthError):
    """Raised when a JWT has passed its ``exp`` claim."""

    def __init__(self) -> None:
        super().__init__("Token expired.")


class InvalidToken(AuthError):
    """Raised when a JWT is malformed, has an invalid signature, or is missing claims."""

    def __init__(self) -> None:
        super().__init__("Invalid token.")
