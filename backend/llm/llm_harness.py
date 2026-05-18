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

The call is fully async: cancellation propagates through ``httpx`` so an
in-flight API request is genuinely aborted when the caller's task is
cancelled (e.g. client disconnect, orchestrator dropping a speculative
branch). ``CancelledError`` MUST escape the retry loop unaltered.
"""

import asyncio
import json
import logging
import time
from uuid import UUID

import openai
from pydantic import BaseModel, ValidationError

from backend.logging_setup import log_llm_call
from backend.settings import PROJECT_ROOT, get_env, get_settings
from backend.llm.types import CostLimitExceeded, LLMParseError, LLMResponse

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


async def call(
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
    response_schema: type[BaseModel] | None = None,
) -> LLMResponse:
    """Make a single LLM chat-completion call with logging, retry, and cost guard.

    When ``response_schema`` is provided, the harness switches the underlying
    chat-completion to JSON-object mode, parses the response, and validates it
    against the supplied Pydantic model. Parse and validation failures consume
    the same retry budget as transient API errors (``_MAX_ATTEMPTS``); after
    exhaustion the harness raises ``LLMParseError`` with the last raw payload.
    The validated model is returned on ``LLMResponse.parsed``.

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
        response_schema:      Optional Pydantic model the response must validate against.
                              When set, JSON-mode is enabled and the harness owns parse
                              + retry; ``LLMResponse.parsed`` carries the validated value.

    Returns:
        An ``LLMResponse`` with the model's reply text and token/latency data.
        ``LLMResponse.parsed`` is the validated Pydantic instance when
        ``response_schema`` was set, otherwise ``None``.

    Raises:
        CostLimitExceeded:   If ``accumulated_cost_usd >= cost_limit_usd`` before the call.
        LLMParseError:       If ``response_schema`` was set and the model returned an
                             invalid payload on all ``_MAX_ATTEMPTS`` attempts.
        openai.RateLimitError / APITimeoutError / APIConnectionError:
                             If all 3 retry attempts fail on a transient error.
        openai.APIError:     On any non-transient API error (raised immediately, no retry).
    """
    # dry_run resolves to True when either the caller passes dry_run=True or
    # any active model tier sets dry_run=true (smoke-test mode). It is
    # evaluated before the cost guard because a fixture response accrues no
    # real cost, so the guard would spuriously reject configs with zero budget.
    _cfg_models = get_settings().models
    effective_dry_run = dry_run or _cfg_models.strong.dry_run or _cfg_models.fast.dry_run
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
        parsed = _validate_response(content, response_schema, step_type) if response_schema else None
        return LLMResponse(
            content=content,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0.0,
            parsed=parsed,
        )

    log.debug(
        "llm_call pre-call",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "step_type": step_type,
            "prompt_hash": prompt_hash,
            "model": model_and_version,
            "provider": provider,
            "accumulated_cost_usd": accumulated_cost_usd,
            "cost_limit_usd": cost_limit_usd,
            "cost_remaining_usd": cost_limit_usd - accumulated_cost_usd,
            "has_schema": response_schema is not None,
        },
    )

    if accumulated_cost_usd >= cost_limit_usd:
        raise CostLimitExceeded(accumulated_cost_usd, cost_limit_usd)

    last_exc: Exception | None = None
    last_raw: str | None = None
    for attempt in range(_MAX_ATTEMPTS):
        if attempt > 0:
            # asyncio.sleep is a cancellation point — if the caller's task is
            # cancelled between attempts, CancelledError raises here and exits
            # the retry loop cleanly. Never catch it.
            await asyncio.sleep(_backoff(attempt))
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
            if response_schema is not None:
                kwargs["response_format"] = {"type": "json_object"}
            response = await _client(provider).chat.completions.create(**kwargs)
            latency_ms = (time.monotonic() - t0) * 1000.0
        except _TRANSIENT_ERRORS as exc:
            last_exc = exc
            continue
        except openai.APIError:
            raise

        if not response.choices:
            last_exc = RuntimeError(
                f"API returned empty choices for step {step_type!r}"
            )
            continue
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        content = response.choices[0].message.content or ""
        last_raw = content

        parsed: BaseModel | None = None
        if response_schema is not None:
            try:
                parsed = _validate_response(content, response_schema, step_type)
            except LLMParseError as exc:
                # Parse / schema failure consumes the same retry budget as a transient
                # API error. We log the call (the request DID hit the API and burn tokens)
                # before continuing so the failed attempt is auditable.
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
                last_exc = exc
                continue

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
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            parsed=parsed,
        )

    if isinstance(last_exc, LLMParseError):
        raise LLMParseError(step_type=step_type, raw=last_raw or "")
    raise last_exc  # type: ignore[misc]


def _validate_response(
    content: str,
    schema: type[BaseModel],
    step_type: str,
) -> BaseModel:
    """Parse *content* as JSON and validate it against *schema*.

    Raises ``LLMParseError`` (with the raw payload) on either a JSON decode
    failure or a Pydantic validation error.  Callers in the retry loop catch
    this and either continue or re-raise after exhausting attempts.
    """
    try:
        return schema.model_validate_json(content)
    except (ValidationError, json.JSONDecodeError) as exc:
        log.debug(
            "llm_call schema validation failed",
            extra={"step_type": step_type, "error": str(exc)[:200]},
        )
        raise LLMParseError(step_type=step_type, raw=content) from exc


_clients: dict[str, openai.AsyncOpenAI] = {}

_PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
}


def _client(provider: str = "openai") -> openai.AsyncOpenAI:
    """Return the shared async client for *provider*, creating it on first call."""
    if provider not in _clients:
        env = get_env()
        if provider == "openrouter":
            if not env.openrouter_api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY is not set. Add it to .env when using provider=openrouter."
                )
            _clients[provider] = openai.AsyncOpenAI(
                base_url=_PROVIDER_BASE_URLS["openrouter"],
                api_key=env.openrouter_api_key,
            )
        else:
            if not env.openai_api_key:
                raise ValueError(
                    "OPENAI_API_KEY is not set. Add it to .env when using provider=openai."
                )
            _clients[provider] = openai.AsyncOpenAI(api_key=env.openai_api_key)
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
