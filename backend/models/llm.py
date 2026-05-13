"""LLM-related models: response type and domain exceptions for the harness."""

from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Result of a single LLM call, returned by ``backend.llm_harness.call()``.

    Attributes:
        content:       Raw text produced by the model.
        input_tokens:  Prompt tokens consumed (billed separately from output).
        output_tokens: Completion tokens produced.
        latency_ms:    Wall-clock duration of the API call in milliseconds.
        cost_usd:      Estimated USD cost based on token counts and model pricing.
    """

    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float = 0.0


class CostLimitExceeded(Exception):
    """Raised by ``llm_harness.call()`` when the session cost budget is exhausted.

    The check is performed *before* making the API call so the session never
    silently overruns its budget.

    Attributes:
        accumulated: Total USD spent so far in the session.
        limit:       The configured ``cost_limit_usd`` ceiling.
    """

    def __init__(self, accumulated: float, limit: float) -> None:
        self.accumulated = accumulated
        self.limit = limit
        super().__init__(
            f"Cost limit ${limit:.4f} reached (accumulated ${accumulated:.4f})"
        )


class LLMParseError(Exception):
    """Raised by an agent after exhausting parse retries on an LLM response.

    The harness always returns the raw content string; it is the agent's
    responsibility to parse it (e.g. as JSON).  If all retry attempts fail,
    the agent raises this exception rather than silently returning stale data.

    Attributes:
        step_type: The ``f_*`` function or agent step that triggered the call.
        raw:       The unparseable string returned by the model.
    """

    def __init__(self, step_type: str, raw: str) -> None:
        self.step_type = step_type
        self.raw = raw
        super().__init__(f"Failed to parse LLM output for step '{step_type}'")
