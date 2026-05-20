"""Immutable per-turn snapshot.

``TurnContext`` freezes everything ``TurnRunner.run`` and its helpers
need to read about the turn: inputs from the caller, derived views over
the session history, and the active ``Settings``. Constructed once via
``TurnContext.build`` at the top of a turn; never mutated after that.

Pushing this state into a frozen dataclass keeps the runner itself
small and makes the "what can a helper see?" question one-line clear:
the helper takes a ``TurnContext``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from backend.repository.sessions import SessionRow, TurnRow
from backend.orchestrator.utils import history
from backend.orchestrator.turn.progress import NullProgressCallback, ProgressCallback
from backend.settings import Settings, get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TurnContext:
    """Frozen per-turn snapshot. Every field is set once, in ``build``.

    Attributes:
        session_id:            Target session UUID.
        user_message:          Oracle's message for this turn.
        turn_id:               Pre-allocated turn UUID.
        turn_number:           1-based index for this turn (len(prior) + 1).
        cfg:                   Active settings snapshot.
        full_session:          Full read-side session snapshot as loaded
                               by ``api_retrieval.get_session_full``.
        prior_profile:         The N-1 preference profile, or None on
                               the truly-first turn.
        recent_turns:          Last 2 turns, fed to the profile agent.
        prior_clustered:       Most recent turn that persisted a non-empty
                               cluster set, or None on the first clustered
                               turn of the session.
        prior_seen:            Titles already shown to the oracle, taken
                               from ``prior_profile["seen_films"]``.
        recommended_last_turn: Titles included in the most recent show
                               turn's recommendation; consumed by the
                               state gate.
        progress_cb:           Streaming callback. Invoked at step
                               boundaries and on the cluster snapshot.
    """

    session_id: UUID
    user_message: str
    turn_id: UUID
    turn_number: int
    cfg: Settings
    full_session: SessionRow
    prior_profile: dict | None
    recent_turns: list[TurnRow]
    prior_clustered: TurnRow | None
    prior_seen: list[str]
    recommended_last_turn: list[str]
    progress_cb: ProgressCallback

    @classmethod
    def build(
        cls,
        *,
        session_id: UUID,
        user_message: str,
        full_session: SessionRow,
        progress_cb: ProgressCallback = NullProgressCallback(),
    ) -> TurnContext:
        """Derive all per-turn state from the caller's inputs.

        Reads ``Settings`` once via ``get_settings()`` so every helper sees
        the same config snapshot. Emits the same two log records the old
        ``TurnRunner.__init__`` emitted.
        """
        cfg = get_settings()
        turn_id = uuid4()
        turn_number = len(full_session.turns) + 1
        prior_profile = full_session.preference_profile
        recent_turns = full_session.turns[-2:]
        prior_clustered = history.last_clustered_turn(full_session.turns)
        prior_seen = (
            list(prior_profile.get("seen_films", [])) if prior_profile else []
        )
        recommended_last_turn = history.recommended_titles_from_last_show(full_session)

        log.debug(
            "turn entry",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "turn_number": turn_number,
                "user_message_len": len(user_message),
                "prior_turns": len(full_session.turns),
            },
        )
        if prior_clustered is not None:
            log.info(
                "refining prior clusters",
                extra={
                    "session_id": str(session_id),
                    "turn_number": turn_number,
                    "prior_clustered_turn_id": str(prior_clustered.id),
                },
            )

        return cls(
            session_id=session_id,
            user_message=user_message,
            turn_id=turn_id,
            turn_number=turn_number,
            cfg=cfg,
            full_session=full_session,
            prior_profile=prior_profile,
            recent_turns=recent_turns,
            prior_clustered=prior_clustered,
            prior_seen=prior_seen,
            recommended_last_turn=recommended_last_turn,
            progress_cb=progress_cb,
        )


__all__ = ["TurnContext"]
