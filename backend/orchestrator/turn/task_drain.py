"""Generic asyncio task drain helpers for the UNDERSTAND wave.

Both helpers are used on speculative *and* profile tasks, so they live
here rather than inside ``speculative``.

* ``cancel_and_drain``    — re-raises any non-cancellation exception so
                            sibling-task failures cannot be hidden.
* ``discard_speculative`` — swallows + logs; used on terminal verdicts
                            where the task's result is unwanted and its
                            failure must not break the bypass turn.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

log = logging.getLogger(__name__)


async def cancel_and_drain(task: asyncio.Task | None) -> None:
    """Cancel *task* and swallow the resulting ``CancelledError``.

    Re-raises any other exception the task surfaced, so we never silently
    discard a real failure on a background branch. Returning early when
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
    background branch's result is no longer needed and its failure must
    not propagate. ``CancelledError`` is swallowed silently; other
    exceptions are logged once as ``WARNING`` and then suppressed.

    Args:
        task: An ``asyncio.Task`` to cancel, or None.
        name: Label used in the warning log record.
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
            "background agent failed (discarded — state terminal)",
            extra={"agent": name, "error": str(exc)},
        )


__all__ = ["cancel_and_drain", "discard_speculative"]
