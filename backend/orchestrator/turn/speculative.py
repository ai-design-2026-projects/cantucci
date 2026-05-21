"""Speculative branch primitives used by the orchestrator.

Each turn's UNDERSTAND phase runs three ``asyncio`` tasks in parallel:
the state gate, profile extraction, and one speculative clustering
branch. This module owns the pure speculative primitives — which branch
to launch and how to chain retrieval and clustering inside it. The
verdict-driven dispatch (consume vs cancel vs re-retrieve) lives in
``backend.orchestrator.turn.tasks.TurnTasks.resolve_clusters``.

The caller (``TurnTasks.spawn``) decides which branch to launch based on
``ctx.prior_clustered``:

* ``spawn_refine``       — prior turn has clusters → launch
                           ``cluster_agent.refine``.
* ``spawn_retrieve_msg`` — no prior clusters → launch
                           ``retrieve_from_message → soft_cluster →
                           describe``.

Task-drain helpers live in ``backend.orchestrator.turn.task_drain``.

Cancellation of the FastAPI request task propagates as
``asyncio.CancelledError`` through these tasks, closing the in-flight
``httpx`` connection inside the async LLM harness, so abandoned OpenAI
calls genuinely abort rather than completing and billing.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import TYPE_CHECKING

import backend.retrieval.agent as retrieval_agent
from backend.repository.sessions.types import ClusterRow
from backend.cluster import cluster_agent
from backend.retrieval.types import RetrievalResult

if TYPE_CHECKING:
    from backend.repository.sessions.types import TurnRow
    from backend.orchestrator.turn.context import TurnContext

log = logging.getLogger(__name__)


class SpeculativeBranch(str, Enum):
    """
    Which branch the orchestrator speculatively launched alongside the state gate.

    Attributes:
        REFINE:       Refinement turn — ``cluster_agent.refine`` was launched.
        RETRIEVE_MSG: Fresh turn — ``retrieval_agent.retrieve_from_message``
                      → ``cluster_agent.describe_clusters`` was launched.
        NONE:         No speculative branch has been launched yet (initial value).
    """
    REFINE = "refine"
    RETRIEVE_MSG = "retrieve_msg"
    NONE = "none"


def spawn_refine(ctx: "TurnContext", prior_clustered: "TurnRow") -> asyncio.Task:
    """Spawn ``cluster_agent.refine`` over *prior_clustered*.

    Used when a previous turn already produced a cluster set. The
    refinement branch is our optimistic "proceed" path — faster than a
    fresh retrieval and more likely to yield coherent results.

    Args:
        ctx:             Frozen per-turn snapshot.
        prior_clustered: The most recent turn that persisted a non-empty
                         cluster set. Caller guarantees it is not None.

    Returns:
        A running ``asyncio.Task`` whose result is a list of
        ``ClusterRow`` values (the refined clusters).
    """
    return asyncio.create_task(
        cluster_agent.refine(
            prior_clusters=list(prior_clustered.clusters),
            user_query=ctx.user_message,
            system_message=prior_clustered.assistant_message or "",
            oracle_reply=ctx.user_message,
            session_id=ctx.session_id,
            run_id=ctx.full_session.run_id,
            turn_id=ctx.turn_id,
        ),
        name="refine_speculative",
    )


def spawn_retrieve_msg(ctx: "TurnContext") -> asyncio.Task:
    """Spawn a full ``retrieve_from_message → soft_cluster → describe`` chain.

    Used when no prior clustered turn exists. This is the "re-retrieve"
    branch — launched speculatively so results are ready if the state
    gate says "proceed" and the oracle's first real preference signal
    lands here.

    Args:
        ctx: Frozen per-turn snapshot.

    Returns:
        A running ``asyncio.Task`` whose result is a list of
        ``ClusterRow`` values (freshly clustered results).
    """
    return asyncio.create_task(
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

    Wrapped as a single coroutine so the orchestrator can cancel the
    whole chain in one call when state invalidates the speculative
    branch. Cancellation between retrieval and clustering, or
    mid-LLM-describe, all propagate via ``CancelledError``.

    Args:
        user_query:   Raw oracle message used as the retrieval query.
        cfg:          Active session settings.
        session_id:   Target session UUID.
        run_id:       Parent run UUID.
        turn_id:      Pre-allocated turn UUID.
        turn_number:  1-based turn index.

    Returns:
        List of ``ClusterRow`` values; empty if retrieval or clustering
        produces no candidates.
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

    Args:
        rr:           Pre-fetched retrieval result.
        user_query:   Original oracle query, passed to the LLM describer.
        cfg:          Active session settings.
        session_id:   Target session UUID.
        run_id:       Parent run UUID.
        turn_id:      Pre-allocated turn UUID.
        turn_number:  1-based turn index.

    Returns:
        List of ``ClusterRow`` values; empty when HDBSCAN yields nothing.
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
    "cluster_from_retrieval",
    "retrieve_msg_then_cluster",
    "spawn_refine",
    "spawn_retrieve_msg",
]
