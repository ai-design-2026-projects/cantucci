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
from backend.settings import PROJECT_ROOT, get_env, get_settings
from backend.llm.types import CostLimitExceeded, LLMResponse

_DRY_RUN_FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "dry_run"

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
    provider: str = "openai",
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
        provider:             API provider — ``"openai"`` (default) or ``"openrouter"``.
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
    # dry_run resolves to True when either the caller passes dry_run=True or
    # the active YAML config sets model.dry_run=true (smoke-test mode). It is
    # evaluated before the cost guard because a fixture response accrues no
    # real cost, so the guard would spuriously reject configs with zero budget.
    effective_dry_run = dry_run or get_settings().model.dry_run
    if effective_dry_run:
        fixture_path = _DRY_RUN_FIXTURES_DIR / f"{step_type}.json"
        if not fixture_path.is_file():
            raise FileNotFoundError(
                f"dry_run fixture missing for step_type '{step_type}' at {fixture_path}. "
                "Add a JSON fixture so the agent's parser receives a well-formed response."
            )
        content = fixture_path.read_text()
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
            input_tokens=0,
            output_tokens=0,
            latency_ms=0.0,
        )
        return LLMResponse(content=content, input_tokens=0, output_tokens=0, latency_ms=0.0)

    if accumulated_cost_usd >= cost_limit_usd:
        raise CostLimitExceeded(accumulated_cost_usd, cost_limit_usd)

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
            kwargs: dict = dict(
                model=model_and_version,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
            )
            if provider == "openai":
                kwargs["seed"] = seed
            response = _client(provider).chat.completions.create(**kwargs)
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


_clients: dict[str, openai.OpenAI] = {}

_PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
}


def _client(provider: str = "openai") -> openai.OpenAI:
    """Return the shared client for *provider*, creating it on first call."""
    if provider not in _clients:
        env = get_env()
        if provider == "openrouter":
            if not env.openrouter_api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY is not set. Add it to .env when using provider=openrouter."
                )
            _clients[provider] = openai.OpenAI(
                base_url=_PROVIDER_BASE_URLS["openrouter"],
                api_key=env.openrouter_api_key,
            )
        else:
            if not env.openai_api_key:
                raise ValueError(
                    "OPENAI_API_KEY is not set. Add it to .env when using provider=openai."
                )
            _clients[provider] = openai.OpenAI(api_key=env.openai_api_key)
    return _clients[provider]


def _backoff(attempt: int) -> float:
    """Return exponential backoff delay in seconds for a given attempt index."""
    return float(2**attempt)


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost from token counts using the _COST_PER_M pricing table."""
    for prefix, rates in _COST_PER_M.items():
        if model.startswith(prefix):
            return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    log.warning("unknown model for cost estimation, charging 0", extra={"model": model})
    return 0.0
