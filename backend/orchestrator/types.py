"""Convergence types shared between convergence.py and orchestrator.py.

These live in a dedicated types module because they cross the convergence →
orchestrator package boundary: convergence.py produces them, orchestrator.py
consumes them.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class ConvergenceAction(str, Enum):
    """Outcome of a single convergence-gate evaluation.

    Attributes:
        proceed:       Normal pipeline should run this turn.
        terminate:     Hard limit hit; abandon the session without LLM calls.
        natural_end:   LLM detected that the oracle wrapped up the conversation.
        clarify_drift: LLM detected a preference contradiction; emit clarification.
    """

    proceed = "proceed"
    terminate = "terminate"
    natural_end = "natural_end"
    clarify_drift = "clarify_drift"


@dataclass(frozen=True)
class ConvergenceDecision:
    """Result returned by every gate function.

    The orchestrator branches on ``.action`` and uses ``.reply`` when it
    needs to emit a system message without running the normal pipeline.

    Attributes:
        action:            What the orchestrator should do this turn.
        reason:            One-line rationale (structured log field).
        reply:             Canned or LLM-generated assistant message, populated
                           for terminate / natural_end / clarify_drift actions.
        drift_topic:       Subject of the contradiction (clarify_drift only).
        prior_statement:   Earlier oracle utterance about the drift topic.
        current_statement: Contradicting utterance in the current turn.
    """

    action: ConvergenceAction
    reason: str
    reply: str | None = None
    drift_topic: str | None = None
    prior_statement: str | None = None
    current_statement: str | None = None


class ConvergenceCheckResponse(BaseModel):
    """JSON schema enforced on the LLM gate response via llm_harness response_schema.

    Attributes:
        decision:          Gate outcome — one of proceed / natural_end / clarify_drift.
        reason:            One-sentence rationale for logging.
        drift_topic:       What the contradiction is about (clarify_drift only).
        prior_statement:   What the oracle said earlier about this topic.
        current_statement: What the oracle said now that contradicts it.
        farewell_reply:    Assistant message to emit on natural_end.
        clarify_reply:     Assistant message to emit on clarify_drift.
    """

    decision: Literal["proceed", "natural_end", "clarify_drift"]
    reason: str
    drift_topic: str | None = None
    prior_statement: str | None = None
    current_statement: str | None = None
    farewell_reply: str | None = None
    clarify_reply: str | None = None
