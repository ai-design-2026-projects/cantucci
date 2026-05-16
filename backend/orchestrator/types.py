"""Convergence types — re-exported from backend.convergence.types.

Kept for backwards-compatibility with existing imports that reference
backend.orchestrator.types. New code should import from backend.convergence.types
directly.
"""

from backend.convergence.types import (  # noqa: F401
    ConvergenceAction,
    ConvergenceCheckResponse,
    ConvergenceDecision,
)
