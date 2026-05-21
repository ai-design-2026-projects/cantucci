import asyncio
import hashlib
import json
import logging
from uuid import UUID
import openai
from pydantic import BaseModel

from backend.logging_setup import log_llm_call
from backend.settings import get_settings
from backend.llm.exceptions import CostLimitExceeded, LLMParseError
from backend.llm.types import LLMResponse
from backend.llm.utils import client as _client_mod
from backend.llm.utils import retry as _retry_mod
from backend.llm.utils.dry_run import dry_run_response
from backend.llm.utils.pricing import estimate_cost
from demo.record_replay import is_record_mode, is_replay_mode, record_append, replay_next
from backend.llm.utils.schema_validation import validate_response

log = logging.getLogger(__name__)


async def call(
    *,
    run_id: str | UUID,
    conversation_id: str | UUID,
    message_id: str | UUID,
    config_hash: str,
    model_and_version: str,
    provider: str = "openai",
    seed: int,
    max_tokens: int,
    step_type: str,
    messages: list[dict[str, str]],
    cost_limit_usd: float,
    accumulated_cost_usd: float,
    dry_run: bool = False,
    response_schema: type[BaseModel] | None = None,
) -> LLMResponse:
    """Make a single LLM chat-completion call with logging, retry, and cost guard.

    When ``response_schema`` is provided, the harness switches the underlying
    chat-completion to JSON-object mode, parses the response, and validates it
    against the supplied Pydantic model. Parse and validation failures consume
    the same retry budget as transient API errors; after exhaustion the harness
    raises ``LLMParseError`` with the last raw payload. The validated model is
    returned on ``LLMResponse.parsed``.

    Args:
        run_id:               Experiment run identifier for logging.
        conversation_id:      Conversation identifier for logging.
        message_id:           Message identifier for logging.
        config_hash:          SHA-256 prefix of the YAML config in effect.
        model_and_version:    Full model string from config, e.g. ``"gpt-4o-2024-08-06"``.
        provider:             API provider — ``"openai"`` (default) or ``"openrouter"``.
        seed:                 RNG seed from config (for reproducibility).
        max_tokens:           Maximum completion tokens from config.
        step_type:            Name of the calling agent step, e.g. ``"intent_agent"``.
        messages:             Chat messages in ``[{"role": ..., "content": ...}]`` form.
        cost_limit_usd:       Per-conversation cost ceiling from config.
        accumulated_cost_usd: Total USD spent so far this conversation (caller-tracked).
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
                             invalid payload on all retry attempts.
        openai.RateLimitError / APITimeoutError / APIConnectionError:
                             If all retry attempts fail on a transient error.
        openai.APIError:     On any non-transient API error (raised immediately, no retry).
    """
    prompt_hash = hashlib.sha256(
        json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:8]
    _cfg_models = get_settings().models
    effective_dry_run = dry_run or _cfg_models.strong.dry_run or _cfg_models.fast.dry_run
    if effective_dry_run:
        return dry_run_response(
            step_type=step_type,
            response_schema=response_schema,
            run_id=run_id,
            session_id=conversation_id,
            turn_id=message_id,
            seed=seed,
            config_hash=config_hash,
            model_and_version=model_and_version,
            prompt_hash=prompt_hash,
        )

    if is_replay_mode():
        return await replay_next(
            session_id=str(conversation_id),
            step_type=step_type,
            run_id=run_id,
            turn_id=message_id,
            seed=seed,
            config_hash=config_hash,
            model_and_version=model_and_version,
            prompt_hash=prompt_hash,
            response_schema=response_schema,
        )

    log.debug(
        "llm_call pre-call",
        extra={
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
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
    for attempt in range(_retry_mod.MAX_ATTEMPTS):
        if attempt > 0:
            # asyncio.sleep is a cancellation point — if the caller's task is
            # cancelled between attempts, CancelledError raises here and exits
            # the retry loop cleanly. Never catch it.
            await asyncio.sleep(_retry_mod.backoff(attempt))
            log.warning(
                "llm_call retry",
                extra={
                    "attempt": attempt + 1,
                    "step_type": step_type,
                    "conversation_id": str(conversation_id),
                    "error": str(last_exc),
                },
            )
        try:
            import time
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
            response = await _client_mod.get_client(provider).chat.completions.create(**kwargs)
            latency_ms = (time.monotonic() - t0) * 1000.0
        except _retry_mod.TRANSIENT_ERRORS as exc:
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
                parsed = validate_response(content, response_schema, step_type)
            except LLMParseError as exc:
                # Parse / schema failure consumes the same retry budget as a transient
                # API error. We log the call (the request DID hit the API and burn tokens)
                # before continuing so the failed attempt is auditable.
                log_llm_call(
                    log,
                    run_id=run_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
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
            conversation_id=conversation_id,
            message_id=message_id,
            seed=seed,
            config_hash=config_hash,
            model_and_version=model_and_version,
            prompt_hash=prompt_hash,
            step_type=step_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

        cost = estimate_cost(model_and_version, input_tokens, output_tokens)
        resp = LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            parsed=parsed,
        )
        if is_record_mode():
            record_append(str(conversation_id), step_type, str(message_id), resp)
        return resp

    if isinstance(last_exc, LLMParseError):
        raise LLMParseError(step_type=step_type, raw=last_raw or "")
    raise last_exc  # type: ignore[misc]
