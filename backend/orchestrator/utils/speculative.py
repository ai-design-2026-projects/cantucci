"""
Speculative branch primitives used by the orchestrator.

Each turn's UNDERSTAND phase runs three ``asyncio`` tasks in parallel:
the state gate, profile extraction, and one speculative clustering
branch. This module owns the pure speculative primitives — which branch
to launch, how to chain retrieval and clustering inside it, and how to
drain it. The verdict-driven dispatch (consume vs cancel vs re-retrieve)
lives in ``backend.orchestrator.turn.tasks.TurnTasks.resolve_clusters``.

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

if TYPE_CHECKING:
    from backend.orchestrator.turn.context import TurnContext

log = logging.getLogger(__name__)


class SpeculativeBranch(str, Enum):
    """
    Which branch the orchestrator speculatively launched alongside the state gate.
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


def spawn(*, ctx: "TurnContext") -> tuple[SpeculativeBranch, asyncio.Task | None]:
    """
    Spawn the one speculative branch appropriate for *ctx*'s turn. We can
    distinguish two cases:
    
    1. Refinement: if the prior turn clustered something, we launch a
       refinement branch to update those clusters in light of the new
       message. This is faster and more likely to yield results than a
       fresh retrieval, so it's our optimistic "proceed" branch.
    
    2. Fresh retrieval: if the prior turn had no clusters, we launch a
       full retrieval+clustering pass on the new message, since there's no
       existing clustered state to refine. This is the "re-retrieve" branch
       we fall back to when the state gate detects drift but the user seems
       to have dismissed it.
    Args:
        ctx: Frozen per-turn snapshot — provides session/turn ids,
             cfg, and ``prior_clustered``.
    Returns:
        Tuple of (branch kind, task). On the refinement branch the task
        is always returned; on the retrieve path it is also always
        returned (never None in current code).
    """
    if ctx.prior_clustered is not None:
        spec_t = asyncio.create_task(
            cluster_agent.refine(
                prior_clusters=list(ctx.prior_clustered.clusters),
                user_query=ctx.user_message,
                system_message=ctx.prior_clustered.assistant_message or "",
                oracle_reply=ctx.user_message,
                session_id=ctx.session_id,
                run_id=ctx.full_session.run_id,
                turn_id=ctx.turn_id,
            ),
            name="refine_speculative",
        )
        return SpeculativeBranch.REFINE, spec_t

    spec_t = asyncio.create_task(
        retrieve_msg_then_cluster(
            user_query=ctx.user_message,
            cfg=ctx.cfg,
            session_id=ctx.session_id,
            run_id=ctx.full_session.run_id,
            turn_id=ctx.turn_id,
            turn_number=ctx.turn_number,
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


__all__ = [
    "SpeculativeBranch",
    "cancel_and_drain",
    "cluster_from_retrieval",
    "discard_speculative",
    "retrieve_msg_then_cluster",
    "spawn",
]
