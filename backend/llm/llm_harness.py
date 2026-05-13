"""Single gateway for all LLM calls in the CinePal backend.

Every agent must call ``llm_harness.call()`` — never instantiate an OpenAI
(or any other) client directly.  This module enforces:

- Structured logging of every call via ``log_llm_call``.
- A pre-call cost guard that raises ``CostLimitExceeded`` when the session
  budget is exhausted.
- Retry with exponential backoff (max 3 attempts) for transient API errors.
- A ``dry_run`` mode that returns a canned response without hitting the API,
  used by component tests.

The OpenAI client is a module-level singleton so the underlying ``httpx``
connection pool is reused across calls, saving TCP + TLS setup per round-trip.
The client itself carries no per-session state — only the API key — so
reuse is safe.
"""

import logging
import time
from uuid import UUID

import openai

from backend.logging_setup import log_llm_call
from backend.settings import get_env
from backend.llm.types import CostLimitExceeded, LLMResponse

log = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3

# USD per million tokens for known model families.  Used to estimate cost_usd
# on each LLMResponse.  Models are matched by prefix so version suffixes are
# tolerated (e.g. "gpt-4o-mini-2024-07-18" matches "gpt-4o-mini").
_COST_PER_M: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "claude-opus": {"input": 15.0, "output": 75.0},
    "claude-sonnet": {"input": 3.0, "output": 15.0},
    "claude-haiku": {"input": 0.80, "output": 4.0},
}

_TRANSIENT_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
)


def call(
    *,
    run_id: str | UUID,
    session_id: str | UUID,
    turn_id: str | UUID,
    config_hash: str,
    model_and_version: str,
    seed: int,
    max_tokens: int,
    step_type: str,
    messages: list[dict[str, str]],
    prompt_hash: str,
    cost_limit_usd: float,
    accumulated_cost_usd: float,
    dry_run: bool = False,
) -> LLMResponse:
    """Make a single LLM chat-completion call with logging, retry, and cost guard.

    Args:
        run_id:               Experiment run identifier for logging.
        session_id:           Conversation session identifier for logging.
        turn_id:              Turn identifier for logging.
        config_hash:          SHA-256 prefix of the YAML config in effect.
        model_and_version:    Full model string from config, e.g. ``"gpt-4o-2024-08-06"``.
        seed:                 RNG seed from session config (for reproducibility).
        max_tokens:           Maximum completion tokens from config.
        step_type:            Name of the calling agent step, e.g. ``"cluster_agent"``.
        messages:             Chat messages in ``[{"role": ..., "content": ...}]`` form.
        prompt_hash:          SHA-256 prefix of the rendered prompt (from ``backend.prompts``).
        cost_limit_usd:       Per-session cost ceiling from config.
        accumulated_cost_usd: Total USD spent so far this session (caller-tracked).
        dry_run:              If ``True``, skip the API call and return a canned response.

    Returns:
        An ``LLMResponse`` with the model's reply text and token/latency data.

    Raises:
        CostLimitExceeded:   If ``accumulated_cost_usd >= cost_limit_usd`` before the call.
        openai.RateLimitError / APITimeoutError / APIConnectionError:
                             If all 3 retry attempts fail on a transient error.
        openai.APIError:     On any non-transient API error (raised immediately, no retry).
    """
    if accumulated_cost_usd >= cost_limit_usd:
        raise CostLimitExceeded(accumulated_cost_usd, cost_limit_usd)

    if dry_run:
        log.debug(
            "llm_call dry_run",
            extra={"step_type": step_type, "session_id": str(session_id)},
        )
        return LLMResponse(content="[DRY RUN]", input_tokens=0, output_tokens=0, latency_ms=0.0)

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        if attempt > 0:
            time.sleep(_backoff(attempt))
            log.warning(
                "llm_call retry",
                extra={
                    "attempt": attempt + 1,
                    "step_type": step_type,
                    "session_id": str(session_id),
                    "error": str(last_exc),
                },
            )
        try:
            t0 = time.monotonic()
            response = _client().chat.completions.create(
                model=model_and_version,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                seed=seed,
            )
            latency_ms = (time.monotonic() - t0) * 1000.0
        except _TRANSIENT_ERRORS as exc:
            last_exc = exc
            continue
        except openai.APIError:
            raise

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        log_llm_call(
            log,
            run_id=run_id,
            session_id=session_id,
            turn_id=turn_id,
            seed=seed,
            config_hash=config_hash,
            model_and_version=model_and_version,
            prompt_hash=prompt_hash,
            step_type=step_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

        cost = _estimate_cost(model_and_version, input_tokens, output_tokens)
        content = response.choices[0].message.content or ""
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
        )

    raise last_exc  # type: ignore[misc]


_openai_client: openai.OpenAI | None = None


def _client() -> openai.OpenAI:
    """Return the shared OpenAI client, creating it on first call."""
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.OpenAI(api_key=get_env().openai_api_key)
    return _openai_client


def _backoff(attempt: int) -> float:
    """Return exponential backoff delay in seconds for a given attempt index."""
    return float(2**attempt)


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost from token counts using the _COST_PER_M pricing table."""
    for prefix, rates in _COST_PER_M.items():
        if model.startswith(prefix):
            return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    return 0.0
