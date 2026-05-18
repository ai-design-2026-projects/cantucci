"""Per-turn pipeline package.

Owns everything that runs inside one ``Orchestrator.run_turn`` call:
the immutable per-turn snapshot (``TurnContext``), the asyncio task
trio and its cancellation lifecycle (``TurnTasks``), the post-decision
rendering and persistence path (``finalize``), and the thin coordinator
that dispatches between them (``TurnRunner``).

The package is constructed once per turn and discarded — no module-level
state, no caches across turns.
"""

from backend.orchestrator.turn.runner import TurnRunner

__all__ = ["TurnRunner"]
