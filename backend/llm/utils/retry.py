import openai

MAX_ATTEMPTS: int = 3

TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
)


def backoff(attempt: int) -> float:
    """Return exponential backoff delay in seconds for a given attempt index."""
    return float(2**attempt)
