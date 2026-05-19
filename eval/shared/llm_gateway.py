"""Thin async LLM gateway for the eval pipeline.

Independent from ``backend/llm/llm_harness.py`` so Oracle and Judge LLM
spend is tracked separately from the system's per-session budget.  The two
budgets must never be conflated: ``CostLimitExceeded`` (system) and
``EvalCostLimitExceeded`` (eval) are distinct exceptions.

Supports the same provider abstraction (``"openai"`` / ``"openrouter"``) and
the same ``dry_run`` fixture pattern as the backend harness so eval component
tests can run without live API calls.

Dry-run fixture path: ``tests/fixtures/eval_dry_run/<step_type>.json``.
"""

import asyncio
import logging
import time
from pathlib import Path
from uuid import UUID

import openai
from pydantic import BaseModel, ValidationError
import json

from backend.logging_setup import log_llm_call
from backend.settings import PROJECT_ROOT, get_env

log = logging.getLogger(__name__)

_EVAL_DRY_RUN_DIR = PROJECT_ROOT / "tests" / "fixtures" / "eval_dry_run"

_MAX_ATTEMPTS = 3

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


class EvalCostLimitExceeded(Exception):
    """Raised by ``LLMGateway.call()`` when the eval run's LLM budget is exhausted.

    Attributes:
        accumulated: Total USD spent so far in the eval run.
        limit:       The configured ``cost_limit_usd`` ceiling.
    """

    def __init__(self, accumulated: float, limit: float) -> None:
        self.accumulated = accumulated
        self.limit = limit
        super().__init__(
            f"Eval cost limit ${limit:.4f} reached (accumulated ${accumulated:.4f})"
        )


class LLMGateway:
    """Async LLM gateway with its own cost ledger for the eval pipeline.

    One gateway instance is created per eval run (not per session) so costs
    accumulate across the entire run.  ``call()`` raises ``EvalCostLimitExceeded``
    when the run-level budget is exhausted.

    Attributes:
        model_name:       Full model identifier string.
        provider:         API provider — ``"openai"`` or ``"openrouter"``.
        seed:             RNG seed for reproducible completions.
        max_tokens:       Maximum completion tokens per call.
        cost_limit_usd:   Run-level USD budget for this gateway (oracle or judge).
        dry_run:          When ``True``, return fixture responses without hitting the API.
        config_hash:      Config hash for ``log_llm_call`` records.
    """

    def __init__(
        self,
        *,
        model_name: str,
        provider: str,
        seed: int,
        max_tokens: int,
        cost_limit_usd: float,
        dry_run: bool = False,
        config_hash: str = "eval",
    ) -> None:
        """Initialise the gateway.

        Args:
            model_name:      Full model identifier string.
            provider:        ``"openai"`` or ``"openrouter"``.
            seed:            RNG seed.
            max_tokens:      Max completion tokens per call.
            cost_limit_usd:  Run-level USD budget ceiling.
            dry_run:         If ``True``, skip API calls and return fixtures.
            config_hash:     Config hash embedded in ``log_llm_call`` records.
        """
        self.model_name = model_name
        self.provider = provider
        self.seed = seed
        self.max_tokens = max_tokens
        self.cost_limit_usd = cost_limit_usd
        self.dry_run = dry_run
        self.config_hash = config_hash
        self._accumulated_cost: float = 0.0

    @property
    def accumulated_cost(self) -> float:
        """Total USD spent so far across all calls in this gateway instance."""
        return self._accumulated_cost

    async def call(
        self,
        *,
        messages: list[dict[str, str]],
        step_type: str,
        prompt_hash: str,
        run_id: str | UUID = "eval",
        session_id: str | UUID = "eval",
        turn_id: str | UUID = "eval",
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        """Make a single LLM chat-completion call with cost tracking and retry.

        Args:
            messages:        Role-tagged message list for the chat completion.
            step_type:       Step identifier for logging and dry-run fixture lookup.
            prompt_hash:     SHA-256 prefix of the rendered prompt for ``log_llm_call``.
            run_id:          Eval run ID (for log correlation).
            session_id:      Session ID (for log correlation).
            turn_id:         Turn ID (for log correlation).
            response_schema: Optional Pydantic model; enables JSON mode + parse.

        Returns:
            Raw model reply string (or fixture content in dry-run mode).

        Raises:
            EvalCostLimitExceeded:  If ``accumulated_cost >= cost_limit_usd``.
            openai.RateLimitError:  After all retry attempts are exhausted.
            ValueError:             If a dry-run fixture file is missing.
        """
        if self.dry_run:
            fixture_path = _EVAL_DRY_RUN_DIR / f"{step_type}.json"
            if not fixture_path.is_file():
                raise FileNotFoundError(
                    f"Eval dry_run fixture missing for step '{step_type}' at {fixture_path}. "
                    "Add a JSON fixture so the eval component receives a well-formed response."
                )
            content = fixture_path.read_text()
            log_llm_call(
                log,
                run_id=run_id,
                session_id=session_id,
                turn_id=turn_id,
                seed=self.seed,
                config_hash=self.config_hash,
                model_and_version=self.model_name,
                prompt_hash=prompt_hash,
                step_type=step_type,
                input_tokens=0,
                output_tokens=0,
                latency_ms=0.0,
            )
            return content

        if self._accumulated_cost >= self.cost_limit_usd:
            raise EvalCostLimitExceeded(self._accumulated_cost, self.cost_limit_usd)

        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            if attempt > 0:
                await asyncio.sleep(float(2**attempt))
                log.warning(
                    "eval llm_call retry attempt=%d step_type=%s error=%s",
                    attempt + 1, step_type, str(last_exc),
                )
            try:
                t0 = time.monotonic()
                kwargs: dict = dict(
                    model=self.model_name,
                    messages=messages,  # type: ignore[arg-type]
                    max_tokens=self.max_tokens,
                )
                if self.provider == "openai":
                    kwargs["seed"] = self.seed
                if response_schema is not None:
                    kwargs["response_format"] = {"type": "json_object"}
                response = await _client(self.provider).chat.completions.create(**kwargs)
                latency_ms = (time.monotonic() - t0) * 1000.0
            except _TRANSIENT_ERRORS as exc:
                last_exc = exc
                continue
            except openai.APIError:
                raise

            if not response.choices:
                last_exc = RuntimeError(f"API returned empty choices for step {step_type!r}")
                continue

            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            content = response.choices[0].message.content or ""

            if response_schema is not None:
                try:
                    response_schema.model_validate_json(content)
                except (ValidationError, json.JSONDecodeError) as exc:
                    last_exc = RuntimeError(
                        f"eval LLM parse error for step '{step_type}': {exc}"
                    )
                    log_llm_call(
                        log,
                        run_id=run_id, session_id=session_id, turn_id=turn_id,
                        seed=self.seed, config_hash=self.config_hash,
                        model_and_version=self.model_name, prompt_hash=prompt_hash,
                        step_type=step_type, input_tokens=input_tokens,
                        output_tokens=output_tokens, latency_ms=latency_ms,
                    )
                    continue

            cost = _estimate_cost(self.model_name, input_tokens, output_tokens)
            self._accumulated_cost += cost

            log_llm_call(
                log,
                run_id=run_id, session_id=session_id, turn_id=turn_id,
                seed=self.seed, config_hash=self.config_hash,
                model_and_version=self.model_name, prompt_hash=prompt_hash,
                step_type=step_type, input_tokens=input_tokens,
                output_tokens=output_tokens, latency_ms=latency_ms,
            )
            return content

        raise last_exc  # type: ignore[misc]


_clients: dict[str, openai.AsyncOpenAI] = {}

_PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
}


def _client(provider: str = "openai") -> openai.AsyncOpenAI:
    """Return the shared async OpenAI-compatible client for *provider*.

    Args:
        provider: ``"openai"`` or ``"openrouter"``.

    Returns:
        Cached ``openai.AsyncOpenAI`` instance.
    """
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


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost from token counts using the internal pricing table.

    Args:
        model:         Model identifier string.
        input_tokens:  Prompt tokens consumed.
        output_tokens: Completion tokens produced.

    Returns:
        Estimated cost in USD (0.0 for unknown models).
    """
    for prefix, rates in _COST_PER_M.items():
        if model.startswith(prefix):
            return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    log.warning("eval: unknown model for cost estimation, charging 0 model=%s", model)
    return 0.0
