"""State agent types shared between state tools and the orchestrator.

These live in a dedicated types module because they cross the state →
orchestrator package boundary: state_agent produces them, orchestrator.py
consumes them.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class StateAction(str, Enum):
    """Outcome of a single state-gate evaluation.

    Attributes:
        proceed:          Normal pipeline should run this turn.
        terminate:        Hard limit hit; abandon the session without LLM calls.
        natural_end:      LLM detected that the oracle wrapped up the conversation.
        clarify_drift:    LLM detected a preference contradiction; emit clarification.
        drift_confirmed:  Oracle confirmed the preference change; re-retrieve with
                          the drift query and the profile summary.
        drift_dismissed:  Oracle explained away the contradiction; proceed normally
                          with the current-turn retrieval.
        re_retrieve:      Oracle signals they have already seen all recommended films;
                          trigger a fresh retrieval with the same preferences but
                          excluding all previously seen titles.
    """

    proceed = "proceed"
    terminate = "terminate"
    natural_end = "natural_end"
    clarify_drift = "clarify_drift"
    drift_confirmed = "drift_confirmed"
    drift_dismissed = "drift_dismissed"
    re_retrieve = "re_retrieve"


@dataclass(frozen=True)
class StateDecision:
    """Result returned by every gate function.

    The orchestrator branches on ``.action`` and uses ``.reply`` when it
    needs to emit a system message without running the normal pipeline.

    Attributes:
        action:             What the orchestrator should do this turn.
        reason:             One-line rationale (structured log field).
        reply:              Canned or LLM-generated assistant message, populated
                            for terminate / natural_end / clarify_drift actions.
        drift_topic:        Subject of the contradiction (clarify_drift only).
        prior_statement:    Earlier oracle utterance about the drift topic.
        current_statement:  Contradicting utterance in the current turn.
        retrieval_override: When set on a ``proceed`` decision, instructs the
                            orchestrator to discard the speculative cluster result
                            and rerun cluster_agent with this query instead.
    """

    action: StateAction
    reason: str
    reply: str | None = None
    drift_topic: str | None = None
    prior_statement: str | None = None
    current_statement: str | None = None
    retrieval_override: str | None = None


class StateCheckResponse(BaseModel):
    """JSON schema enforced on the LLM gate response via llm_harness response_schema.

    Attributes:
        decision:          Gate outcome.
        reason:            One-sentence rationale for logging.
        drift_topic:       What the contradiction is about (clarify_drift only).
        prior_statement:   What the oracle said earlier about this topic.
        current_statement: What the oracle said now that contradicts it.
        farewell_reply:    Assistant message to emit on natural_end.
        clarify_reply:     Assistant message to emit on clarify_drift.
    """

    decision: Literal[
        "proceed",
        "natural_end",
        "clarify_drift",
        "drift_confirmed",
        "drift_dismissed",
        "re_retrieve",
    ]
    reason: str
    drift_topic: str | None = None
    prior_statement: str | None = None
    current_statement: str | None = None
    farewell_reply: str | None = None
    clarify_reply: str | None = None
