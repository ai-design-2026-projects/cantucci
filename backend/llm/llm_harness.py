"""Single gateway for all LLM calls in the cantucci backend.

Every agent must call ``llm_harness.call()`` — never instantiate an OpenAI
(or any other) client directly.  This module enforces:

- Structured logging of every call via ``log_llm_call``.
- A pre-call cost guard that raises ``CostLimitExceeded`` when the session
  budget is exhausted.
- Retry with exponential backoff (max 3 attempts) for transient API errors.
- A ``dry_run`` mode that returns a canned response without hitting the API,
  used by component tests.

The OpenAI client is constructed inside ``call()`` on every invocation so
there is no module-level mutable state (which would bleed across sessions).
The overhead is negligible compared to a live network round-trip.
"""

import logging
import time
from uuid import UUID

import openai

import backend.config as config
from backend.logging import log_llm_call
from backend.models.llm import CostLimitExceeded, LLMResponse

log = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
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

        content = response.choices[0].message.content or ""
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

    raise last_exc  # type: ignore[misc]


def _client() -> openai.OpenAI:
    """Construct a fresh OpenAI client using the configured API key."""
    return openai.OpenAI(api_key=config.openai_api_key())


def _backoff(attempt: int) -> float:
    """Return exponential backoff delay in seconds for a given attempt index."""
    return float(2**attempt)
