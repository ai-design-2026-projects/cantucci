from uuid import UUID


class ConversationNotFound(Exception):
    """Raised when a conversation_id does not exist in the DB.

    Attributes:
        conversation_id: The UUID that was looked up and not found.
    """

    def __init__(self, conversation_id: UUID) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"Conversation {conversation_id} not found")


class ClusterSnapshotNotFound(Exception):
    """Raised when a cluster_snapshot_id does not exist in the DB.

    Attributes:
        cluster_snapshot_id: The UUID that was looked up and not found.
    """

    def __init__(self, cluster_snapshot_id: UUID) -> None:
        self.cluster_snapshot_id = cluster_snapshot_id
        super().__init__(f"Cluster snapshot {cluster_snapshot_id} not found")


class MovieNotFound(Exception):
    """Raised when a movie_id is not present in the catalogue.

    Attributes:
        movie_id: The TMDB integer ID that was not found.
    """

    def __init__(self, movie_id: int) -> None:
        self.movie_id = movie_id
        super().__init__(f"Movie {movie_id} not found in catalogue")


class ConceptParseError(Exception):
    """Raised when the concept agent cannot parse a user-supplied concept string.

    Attributes:
        raw: The raw concept string that could not be parsed.
    """

    def __init__(self, raw: str) -> None:
        self.raw = raw
        super().__init__(f"Could not parse concept: {raw!r}")
