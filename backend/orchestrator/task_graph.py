"""Tiny task-graph primitives used by the async orchestrator.

The orchestrator runs each turn as an ``asyncio`` task graph rather than as
serial waves so that:

* Speculative branches (refine / retrieve-from-message) can be cancelled
  cleanly as soon as the state gate invalidates them.
* Cancellation of the FastAPI request task propagates into every spawned
  child via ``asyncio.CancelledError``, which closes the in-flight
  ``httpx`` connection inside the async LLM harness and genuinely aborts
  the OpenAI call instead of letting it complete and bill us.

This module deliberately stays tiny — the orchestrator is its only
consumer. Adding more abstraction here would obscure the (already
literate) task graph in ``orchestrator.py``.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from enum import Enum


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


__all__ = ["SpeculativeBranch", "cancel_and_drain"]
