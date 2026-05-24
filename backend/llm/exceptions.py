from backend.exceptions import OperationalError, ParseError


class CostLimitExceeded(OperationalError):
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


class LLMParseError(ParseError):
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


class ReplayDriftError(OperationalError):
    """Raised by ``llm_harness.call()`` when the incoming ``step_type`` does not
    match the next entry in the recorded manifest.

    This indicates that the call sequence has diverged from the recording —
    typically because the config, prompt, or seed changed after the manifest
    was captured.  Re-record the manifest to fix this.

    Attributes:
        expected:   The ``step_type`` stored in the next manifest entry.
        got:        The ``step_type`` of the incoming harness call.
        session_id: The session whose manifest queue is out of sync.
    """

    def __init__(self, expected: str, got: str, session_id: str) -> None:
        self.expected = expected
        self.got = got
        self.session_id = session_id
        super().__init__(
            f"Replay drift in session {session_id!r}: "
            f"expected step_type={expected!r} but got {got!r}. "
            "Re-record the manifest (CINEPAL_LLM_MODE=record)."
        )
