"""Async task lifecycle for the UNDERSTAND wave of a turn.

``TurnTasks`` owns the three concurrent ``asyncio.Task`` handles spawned
at the top of a turn — state gate, profile extraction, speculative
clustering — plus the rules for awaiting, draining, and cancelling them.
The mutable state (task handles, which speculative branch was picked)
lives here so ``TurnRunner`` itself can stay a flat dispatcher over an
immutable ``TurnContext``.

Cancellation contract
---------------------
* ``await_state``/``await_profile`` cancel siblings on failure via
  ``cancel_and_drain`` so a sibling-task failure cannot be hidden.
* ``discard_all`` is used on terminal verdicts (natural_end, drift)
  where the speculative + profile results are no longer needed; their
  failures are logged but not propagated, so the bypass turn always
  completes.
"""
import asyncio
import logging
import backend.retrieval.agent as retrieval_agent
from backend.repository.sessions.types import ClusterRow
from backend.orchestrator.turn.context import TurnContext
from backend.orchestrator.turn.speculative import (
    SpeculativeBranch,
    cluster_from_retrieval,
    spawn_refine,
    spawn_retrieve_msg,
)
from backend.orchestrator.turn.task_drain import cancel_and_drain, discard_speculative
import backend.profile.profile_agent as profile_agent
from backend.profile.types import UserProfile
from backend.state import state_agent
from backend.state.types import StateAction, StateDecision

log = logging.getLogger(__name__)


class TurnTasks:
    """The three-task lifecycle behind the UNDERSTAND wave of a turn."""
    ctx: TurnContext
    state_check: asyncio.Task | None
    profile: asyncio.Task | None
    speculative: asyncio.Task | None
    speculative_kind: SpeculativeBranch

    def __init__(self, ctx: TurnContext) -> None:
        """Bind to *ctx*. No tasks are scheduled until ``spawn`` is called."""
        self.ctx = ctx
        self.state_check = None
        self.profile = None
        self.speculative = None
        self.speculative_kind = SpeculativeBranch.NONE

    def spawn(self) -> None:
        """Schedule state gate, profile extraction, and the speculative branch in parallel."""
        ctx = self.ctx
        # State gate: check the message against the session state and emit a verdict (proceed, natural_end, clarify_drift)
        self.state_check = asyncio.create_task(
            state_agent.check_session_state(
                session_id=ctx.session_id,
                run_id=ctx.full_session.run_id,
                turn_id=ctx.turn_id,
                turn_number=ctx.turn_number,
                user_message=ctx.user_message,
                full=ctx.full_session,
                preference_profile=ctx.prior_profile,
                cfg=ctx.cfg,
                recommended_last_turn=ctx.recommended_last_turn,
                seen_films=ctx.prior_seen,
            ),
            name="state_gate",
        )
        # Profile extraction: summarize the user message and extract preferences to feed into retrieval if the state gate indicates drift or re-retrieval
        self.profile = asyncio.create_task(
            profile_agent.extract(
                session_id=ctx.session_id,
                run_id=ctx.full_session.run_id,
                turn_id=ctx.turn_id,
                turn_number=ctx.turn_number,
                user_message=ctx.user_message,
                prior_profile=ctx.prior_profile,
                recent_turns=ctx.recent_turns,
            ),
            name="profile_extract",
        )
        # Speculative clustering: do a best-effort retrieval + clustering to have results ready in case
        # the state gate says "proceed" or "drift_dismissed".
        # The kind of speculative branch (proceed vs drift) is tracked to know
        # whether we can use the speculative clusters as-is or need to re-retrieve from the profile.
        if ctx.prior_clustered is not None:
            self.speculative = spawn_refine(ctx, ctx.prior_clustered)
            self.speculative_kind = SpeculativeBranch.REFINE
        else:
            self.speculative = spawn_retrieve_msg(ctx)
            self.speculative_kind = SpeculativeBranch.RETRIEVE_MSG

    async def await_state(self) -> StateDecision:
        """Await the state gate; cancel siblings before re-raising on failure."""
        assert self.state_check is not None
        try:
            return await self.state_check
        except BaseException:
            await cancel_and_drain(self.profile)
            await cancel_and_drain(self.speculative)
            raise

    async def await_profile(self) -> UserProfile:
        """Await the profile task; cancel the speculative branch on failure."""
        assert self.profile is not None
        try:
            return await self.profile
        except BaseException:
            await cancel_and_drain(self.speculative)
            raise

    async def discard_all(self) -> None:
        """Drain both background tasks on a terminal verdict — failures swallowed.

        Used on natural_end and clarify_drift, where the speculative
        clustering branch and the profile extraction are no longer needed
        and their failure must not break the bypass turn.
        """
        await discard_speculative(self.speculative, self.speculative_kind.value)
        await discard_speculative(self.profile, "profile")

    async def resolve_clusters(
        self,
        state: StateDecision,
        new_profile: UserProfile,
    ) -> list[ClusterRow]:
        """Convert the state verdict into the final cluster list for this turn.

        Either consumes the speculative branch (proceed / drift_dismissed)
        or cancels it and spawns a profile-driven re-retrieval
        (drift_confirmed, re_retrieve). All ``state.action`` dispatch
        lives here so ``TurnRunner.run`` stays a straight line.

        Returns:
            The cluster list to feed into the decision agent. Empty list
            means retrieval / clustering produced no candidates and the
            runner should route to the empty-clusters bypass.
        """
        ctx = self.ctx
        if state.action in (StateAction.drift_confirmed, StateAction.re_retrieve):
            await cancel_and_drain(self.speculative)
            summary = new_profile.summary or ctx.user_message
            excluded = list(dict.fromkeys(ctx.prior_seen + new_profile.anchor_films))
            log.info(
                "re-retrieving from profile summary",
                extra={
                    "session_id": str(ctx.session_id),
                    "turn_id": str(ctx.turn_id),
                    "state_action": state.action.value,
                    "using_profile_summary": bool(new_profile.summary),
                    "n_excluded_films": len(excluded),
                },
            )
            rr = await retrieval_agent.retrieve_from_profile(
                summary=summary,
                excluded_films=excluded,
                k=ctx.cfg.retrieval.top_k,
                session_id=ctx.session_id,
                run_id=ctx.full_session.run_id,
                turn_id=ctx.turn_id,
            )
            return await cluster_from_retrieval(
                rr,
                user_query=summary,
                cfg=ctx.cfg,
                session_id=ctx.session_id,
                run_id=ctx.full_session.run_id,
                turn_id=ctx.turn_id,
                turn_number=ctx.turn_number,
            )

        if state.action is StateAction.drift_dismissed:
            log.info(
                "drift dismissed — using speculative result",
                extra={
                    "session_id": str(ctx.session_id),
                    "turn_id": str(ctx.turn_id),
                },
            )

        # proceed / drift_dismissed: consume the speculative branch.
        if self.speculative is None:
            return []
        return await self.speculative


__all__ = ["TurnTasks"]
