from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, field_validator

from backend.orchestrator.domain import SessionStatus, StepType
from backend.routers.dto.movies.dtos import MovieDto


class AmbiguityMeta(BaseModel):
    """Metadata for the frontend to render an ask-turn as buttons.

    Attributes:
        ui_format:    Rendering hint — ``"binary"`` for yes/no questions,
                      ``"forced_choice"`` for two-option comparisons.
        cluster_refs: UUIDs of the 2–3 clusters the question targets.
    """

    ui_format: str
    cluster_refs: list[UUID]


class TurnDto(BaseModel):
    """Outcome of a single conversation turn, returned by the orchestrator.

    Attributes:
        turn_id:          UUID of the persisted turn row.
        session_id:       UUID of the owning session.
        turn_number:      1-based index within the session.
        user_message:     The oracle's original message.
        assistant_message: The system's response.
        step_type:        Whether the response shows a result, asks, or stops.
        converged:        True when the session reached a convergence decision.
        created_at:       Server-set UTC timestamp of the turn.
        recommendation:   Structured cluster + films payload for show/stop turns.
    """

    turn_id: UUID
    session_id: UUID
    turn_number: int
    user_message: str
    assistant_message: str
    step_type: StepType
    converged: bool
    created_at: datetime
    ambiguity_meta: AmbiguityMeta | None = None
    recommendation: "RecommendationDto | None" = None


class SessionDto(BaseModel):
    """HTTP representation of a session, used by both the listing and detail endpoints.

    Public fields (serialized to the frontend):
        session_id, status, max_turns, created_at, updated_at,
        turn_count, first_user_message, cluster_snapshot, turns.

    Attributes:
        session_id:          UUID of the session.
        status:              Current lifecycle state.
        max_turns:           Maximum number of turns before forced termination.
        created_at:          Server-set UTC timestamp of session creation.
        updated_at:          Server-set UTC timestamp of the last state change.
        turn_count:          Number of completed turns (populated on both endpoints).
        first_user_message:  Text of the first oracle message, or None.
        cluster_snapshot:    Current cluster state (latest clustered turn's clusters).
        turns:               Ordered list of all turns; empty on the listing endpoint.
    """

    session_id: UUID
    status: SessionStatus
    max_turns: int
    created_at: datetime
    updated_at: datetime
    turn_count: int = 0
    first_user_message: str | None = None
    cluster_snapshot: list["ClusterDto"] = []
    turns: list[TurnDto] = []

    def converged_turn(self) -> "TurnDto | None":
        """Return the turn where convergence was declared, or None.

        Returns:
            The ``TurnDto`` with ``converged=True``, or ``None`` if none exist.
        """
        for turn in reversed(self.turns):
            if turn.converged:
                return turn
        return None

    def last_turn_with_recommendation(self) -> "TurnDto | None":
        """Return the last turn carrying a non-None recommendation, or None.

        Returns:
            ``TurnDto`` with a recommendation, or ``None``.
        """
        for turn in reversed(self.turns):
            if turn.recommendation is not None:
                return turn
        return None

    def transcript(self) -> str:
        """Build a plain-text turn-by-turn transcript.

        Returns:
            Multi-line string with alternating Oracle / CinePal lines.
        """
        lines: list[str] = []
        for turn in self.turns:
            lines.append(f"[Turn {turn.turn_number}]")
            lines.append(f"Oracle: {turn.user_message}")
            lines.append(f"CinePal: {turn.assistant_message}")
            lines.append("")
        return "\n".join(lines)


class TurnRequest(BaseModel):
    """HTTP request body for POST /sessions/{session_id}/turns.

    Attributes:
        user_message: The oracle's message for this turn. Must be non-empty.
    """

    user_message: str

    @field_validator("user_message")
    @classmethod
    def non_empty(cls, v: str) -> str:
        """Reject blank or whitespace-only messages at the HTTP boundary.

        Args:
            v: The raw user_message value from the request body.

        Returns:
            The validated, untrimmed value.

        Raises:
            ValueError: If the string is empty or contains only whitespace.
        """
        if not v.strip():
            raise ValueError("user_message must not be empty or whitespace")
        return v


class SoftScore(BaseModel):
    """Soft assignment score for one movie in a cluster.

    Attributes:
        movie_id:  TMDB movie id.
        score:     Confidence in [0, 1] that this movie belongs to the cluster.
        excluded:  True if the oracle explicitly excluded this movie.
    """

    movie_id: int
    score: float
    excluded: bool


class ClusterDto(BaseModel):
    """A single cluster as exposed to the frontend.

    Attributes:
        id:                Cluster UUID.
        name:              Human-readable cluster label.
        description:       Short description of the cluster's theme.
        level:             1 = coarse, 2 = fine.
        parent_cluster_id: UUID of the parent coarse cluster, or None.
        soft_scores:       Per-movie soft assignment scores.
        top_titles:        All assigned film ids: non-excluded first (score desc), then excluded.
    """

    id: UUID
    name: str
    description: str | None
    level: int
    parent_cluster_id: UUID | None
    soft_scores: list[SoftScore]
    top_titles: list[int]


class RecommendationDto(BaseModel):
    """Structured recommendation payload emitted on show and stop turns.

    Attributes:
        cluster: The cluster selected as best match by the Decision Agent.
        films:   Top-K films in descending score order, fully enriched.
    """

    cluster: ClusterDto
    films: list[MovieDto]


TurnDto.model_rebuild()
SessionDto.model_rebuild()
