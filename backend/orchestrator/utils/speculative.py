"""Speculative branch primitives used by the orchestrator.

Each turn's UNDERSTAND phase runs three ``asyncio`` tasks in parallel:
the state gate, profile extraction, and one speculative clustering
branch. This module owns the speculative side — which branch to launch,
how to chain retrieval and clustering inside it, and how to drain it
once the state gate verdict either consumes or invalidates it.

Two drain helpers, deliberately different:

* ``cancel_and_drain``    — re-raises any non-cancellation exception so
                            sibling-task failures cannot be hidden.
* ``discard_speculative`` — swallows + logs; used on terminal verdicts
                            where the speculative result is unwanted and
                            its failure must not break the bypass turn.

Cancellation of the FastAPI request task propagates as
``asyncio.CancelledError`` through these tasks, closing the in-flight
``httpx`` connection inside the async LLM harness, so abandoned OpenAI
calls genuinely abort rather than completing and billing.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from enum import Enum
from typing import TYPE_CHECKING

import backend.retrieval.agent as retrieval_agent
from backend.api.types import ClusterRow
from backend.cluster import cluster_agent
from backend.retrieval.types import RetrievalResult
from backend.state.types import StateAction, StateDecision

if TYPE_CHECKING:
    from backend.orchestrator.utils.turn_runner import TurnRunner

log = logging.getLogger(__name__)


class SpeculativeBranch(str, Enum):
    """Which branch the orchestrator speculatively launched alongside the state gate.

    Attributes:
        REFINE:       Refinement turn — ``cluster_agent.refine`` was launched.
        RETRIEVE_MSG: Fresh turn — ``retrieval_agent.retrieve_from_message``
                      → ``cluster_agent.describe_clusters`` was launched.
        NONE:         No speculative branch was launched for this turn.
    """

    REFINE = "refine"
    RETRIEVE_MSG = "retrieve_msg"
    NONE = "none"


async def cancel_and_drain(task: asyncio.Task | None) -> None:
    """Cancel *task* and swallow the resulting ``CancelledError``.

    Re-raises any other exception the task surfaced, so we never silently
    discard a real failure on the speculative branch. Returning early when
    *task* is None or already done keeps callers' control flow flat.

    Args:
        task: An ``asyncio.Task`` to cancel, or None.
    """
    if task is None or task.done():
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def discard_speculative(task: asyncio.Task | None, name: str) -> None:
    """Cancel *task* and swallow any exception with a discard warning.

    Used on terminal state paths (natural_end, clarify_drift) where a
    speculative branch's result is no longer needed and its failure must
    not propagate. ``CancelledError`` is swallowed silently; other
    exceptions are logged once as ``WARNING`` and then suppressed.
    """
    if task is None:
        return
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as exc:  # noqa: BLE001 — discarded result; logged.
        log.warning(
            "speculative agent failed (discarded — state terminal)",
            extra={"agent": name, "error": str(exc)},
        )


def spawn(*, runner: TurnRunner) -> tuple[SpeculativeBranch, asyncio.Task | None]:
    """Spawn the one speculative branch appropriate for *runner*'s turn.

    Whenever the session already has clusters from a prior turn we
    speculatively refine them in light of the oracle's reply. Only the
    truly-first clustered turn of a session (and any session whose earlier
    retrievals returned nothing) takes the fresh-retrieval path via
    ``retrieve_from_message → soft_cluster → describe_clusters``.
    State-invalidated speculative work is cancelled once the gate resolves;
    the still-running branch is consumed otherwise.

    Args:
        runner: The active TurnRunner — provides session/turn ids,
                cfg, and ``prior_clustered``.

    Returns:
        Tuple of (branch kind, task). On the refinement branch the task
        is always returned; on the retrieve path it is also always
        returned (never None in current code).
    """
    if runner.prior_clustered is not None:
        spec_t = asyncio.create_task(
            cluster_agent.refine(
                prior_clusters=list(runner.prior_clustered.clusters),
                user_query=runner.user_message,
                system_message=runner.prior_clustered.assistant_message or "",
                oracle_reply=runner.user_message,
                session_id=runner.session_id,
                run_id=runner.full_session.run_id,
                turn_id=runner.turn_id,
            ),
            name="refine_speculative",
        )
        return SpeculativeBranch.REFINE, spec_t

    spec_t = asyncio.create_task(
        retrieve_msg_then_cluster(
            user_query=runner.user_message,
            cfg=runner.cfg,
            session_id=runner.session_id,
            run_id=runner.full_session.run_id,
            turn_id=runner.turn_id,
            turn_number=runner.turn_number,
        ),
        name="retrieve_msg_speculative",
    )
    return SpeculativeBranch.RETRIEVE_MSG, spec_t


async def retrieve_msg_then_cluster(
    *,
    user_query: str,
    cfg,
    session_id,
    run_id,
    turn_id,
    turn_number: int,
) -> list[ClusterRow]:
    """Speculative chain: retrieve_from_message → soft_cluster → describe.

    Wrapped as a single task so the orchestrator can cancel the whole
    chain in one call when state invalidates the speculative branch.
    Cancellation between retrieval and clustering, or mid-LLM-describe,
    all propagate via ``CancelledError``.
    """
    rr = await retrieval_agent.retrieve_from_message(
        user_query=user_query,
        k=cfg.retrieval.top_k,
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
    )
    return await cluster_from_retrieval(
        rr,
        user_query=user_query,
        cfg=cfg,
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        turn_number=turn_number,
    )


async def cluster_from_retrieval(
    rr: RetrievalResult,
    *,
    user_query: str,
    cfg,
    session_id,
    run_id,
    turn_id,
    turn_number: int,
) -> list[ClusterRow]:
    """Run HDBSCAN → LLM describe over an already-fetched ``RetrievalResult``.

    ``soft_cluster`` is sync and CPU-bound (HDBSCAN + embedding fetch); we
    hop into a thread so the event loop stays free for in-flight LLM
    calls on other turns. Returns an empty list when retrieval yields no
    candidates or HDBSCAN classifies all as noise.
    """
    sr = await asyncio.to_thread(
        cluster_agent.soft_cluster,
        retrieval_result=rr,
        session_id=session_id,
        turn_id=turn_id,
        turn_number=turn_number,
    )
    if sr is None:
        return []
    return await cluster_agent.describe_clusters(
        soft_result=sr,
        user_query=user_query,
        reformulated_query=rr.reformulated_query,
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
    )


async def resolve_clusters(
    *,
    state: StateDecision,
    runner: TurnRunner,
    new_profile,
) -> list[ClusterRow]:
    """Convert the state verdict into the final cluster list for *runner*'s turn.

    Either consumes the speculative branch (proceed / drift_dismissed) or
    cancels it and spawns a profile-driven re-retrieval (drift_confirmed,
    re_retrieve). All ``state.action`` dispatch lives here so the rest of
    ``TurnRunner.run`` stays a straight line.

    Args:
        state:       The state agent's verdict for this turn.
        runner:      The active TurnRunner.
        new_profile: Freshly extracted profile (needed for re-retrieval).

    Returns:
        The cluster list to feed into the decision agent. Empty list means
        retrieval / clustering produced no candidates and the orchestrator
        should route to the empty-clusters bypass.
    """
    if state.action in (StateAction.drift_confirmed, StateAction.re_retrieve):
        await cancel_and_drain(runner.speculative_task)
        summary = new_profile.summary or runner.user_message
        excluded = list(dict.fromkeys(runner.prior_seen + new_profile.anchor_films))
        log.info(
            "re-retrieving from profile summary",
            extra={
                "session_id": str(runner.session_id),
                "turn_id": str(runner.turn_id),
                "state_action": state.action.value,
                "using_profile_summary": bool(new_profile.summary),
                "n_excluded_films": len(excluded),
            },
        )
        rr = await retrieval_agent.retrieve_from_profile(
            summary=summary,
            excluded_films=excluded,
            k=runner.cfg.retrieval.top_k,
            session_id=runner.session_id,
            run_id=runner.full_session.run_id,
            turn_id=runner.turn_id,
        )
        return await cluster_from_retrieval(
            rr,
            user_query=summary,
            cfg=runner.cfg,
            session_id=runner.session_id,
            run_id=runner.full_session.run_id,
            turn_id=runner.turn_id,
            turn_number=runner.turn_number,
        )

    if state.action is StateAction.drift_dismissed:
        log.info(
            "drift dismissed — using speculative result",
            extra={"session_id": str(runner.session_id), "turn_id": str(runner.turn_id)},
        )

    # proceed / drift_dismissed: consume the speculative branch.
    if runner.speculative_task is None:
        return []
    return await runner.speculative_task


__all__ = [
    "SpeculativeBranch",
    "cancel_and_drain",
    "cluster_from_retrieval",
    "discard_speculative",
    "resolve_clusters",
    "retrieve_msg_then_cluster",
    "spawn",
]
