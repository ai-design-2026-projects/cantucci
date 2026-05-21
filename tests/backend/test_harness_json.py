"""Unit tests for ``llm_harness.call(response_schema=...)``.

These cover the JSON-mode + Pydantic-validation path, including:
  - successful parse on the first attempt
  - retry-on-malformed-JSON within ``_MAX_ATTEMPTS``
  - schema-validation failure (well-formed JSON, wrong shape)
  - retry budget exhaustion → ``LLMParseError``
  - dry-run fixture validation against the schema

The OpenAI client is monkeypatched at module level so no network is involved.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Iterator
from uuid import uuid4

import pytest
from pydantic import BaseModel

import backend.llm.utils.client as llm_client
import backend.llm.utils.retry as llm_retry
from backend.llm import llm_harness
from backend.llm.types import LLMParseError


class _Schema(BaseModel):
    """Minimal schema used for harness tests."""

    query: str
    excluded_films: list[str]


def _make_response(content: str) -> SimpleNamespace:
    """Shape a fake OpenAI ChatCompletion just enough for the harness to consume."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


class _FakeClient:
    """Stand-in for ``openai.AsyncOpenAI`` that yields scripted responses in order."""

    def __init__(self, payloads: list[str]) -> None:
        self._payloads: Iterator[str] = iter(payloads)
        self.calls: list[dict] = []

        client = self

        class _ChatCompletions:
            async def create(self, **kwargs):  # type: ignore[no-untyped-def]
                client.calls.append(kwargs)
                return _make_response(next(client._payloads))

        self.chat = SimpleNamespace(completions=_ChatCompletions())


@pytest.fixture()
def _no_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the live (non-dry-run) path even when the test config has dry_run=true."""
    import backend.settings as settings

    real = settings.get_settings()
    fake_models = real.models.model_copy(update={
        "strong": real.models.strong.model_copy(update={"dry_run": False}),
        "fast": real.models.fast.model_copy(update={"dry_run": False}),
    })
    fake_settings = real.model_copy(update={"models": fake_models})
    monkeypatch.setattr(settings, "get_settings", lambda: fake_settings)
    # The harness imports get_settings directly, so patch its reference too.
    monkeypatch.setattr(llm_harness, "get_settings", lambda: fake_settings)


@pytest.fixture()
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapse retry backoff to zero so tests don't wait on real sleeps."""
    monkeypatch.setattr(llm_retry, "backoff", lambda _attempt: 0.0)


def _install_fake_client(monkeypatch: pytest.MonkeyPatch, payloads: list[str]) -> _FakeClient:
    fake = _FakeClient(payloads)
    monkeypatch.setattr(llm_client, "_clients", {"openai": fake})
    return fake


async def _call(**overrides):  # type: ignore[no-untyped-def]
    """Invoke the harness with sensible defaults; overrides win."""
    kwargs = dict(
        run_id=uuid4(),
        session_id=uuid4(),
        turn_id=uuid4(),
        config_hash="deadbeef",
        model_and_version="gpt-4o-mini",
        seed=0,
        max_tokens=128,
        step_type="retrieval_reformulate",
        messages=[{"role": "user", "content": "hi — respond as JSON"}],
        prompt_hash="cafef00d",
        cost_limit_usd=1.0,
        accumulated_cost_usd=0.0,
        response_schema=_Schema,
    )
    kwargs.update(overrides)
    return await llm_harness.call(**kwargs)


async def test_call_with_schema_validates_first_attempt(
    _no_dry_run: None, _no_backoff: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid JSON response on the first attempt is parsed and returned."""
    fake = _install_fake_client(
        monkeypatch,
        ['{"query": "a slow burn", "excluded_films": []}'],
    )
    response = await _call()
    assert isinstance(response.parsed, _Schema)
    assert response.parsed.query == "a slow burn"
    assert response.parsed.excluded_films == []
    # JSON-mode should have been requested
    assert fake.calls[0]["response_format"] == {"type": "json_object"}
    assert len(fake.calls) == 1


async def test_call_with_schema_retries_on_malformed_json(
    _no_dry_run: None, _no_backoff: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed JSON consumes one retry; a valid follow-up resolves the call."""
    fake = _install_fake_client(
        monkeypatch,
        [
            "not json at all",
            '{"query": "ok", "excluded_films": ["X"]}',
        ],
    )
    response = await _call()
    assert response.parsed is not None
    assert response.parsed.excluded_films == ["X"]
    assert len(fake.calls) == 2


async def test_call_with_schema_retries_on_validation_error(
    _no_dry_run: None, _no_backoff: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Well-formed JSON with the wrong shape is also retried as a parse failure."""
    fake = _install_fake_client(
        monkeypatch,
        [
            '{"reformulated_query": "wrong field name"}',
            '{"query": "right shape now", "excluded_films": []}',
        ],
    )
    response = await _call()
    assert response.parsed is not None
    assert response.parsed.query == "right shape now"
    assert len(fake.calls) == 2


async def test_call_with_schema_raises_after_exhaustion(
    _no_dry_run: None, _no_backoff: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All three attempts malformed → LLMParseError carrying the final raw payload."""
    fake = _install_fake_client(
        monkeypatch,
        ["nope", "still no", "definitely not"],
    )
    with pytest.raises(LLMParseError) as exc_info:
        await _call()
    assert exc_info.value.step_type == "retrieval_reformulate"
    assert "definitely not" in exc_info.value.raw
    assert len(fake.calls) == 3


async def test_dry_run_validates_fixture_against_schema() -> None:
    """The dry-run fixture for retrieval_reformulate must satisfy the live schema."""
    from backend.retrieval.types import ReformulatedQuery

    response = await llm_harness.call(
        run_id=uuid4(),
        session_id=uuid4(),
        turn_id=uuid4(),
        config_hash="deadbeef",
        model_and_version="gpt-4o-mini",
        seed=0,
        max_tokens=128,
        step_type="retrieval_reformulate",
        messages=[{"role": "user", "content": "anything"}],
        prompt_hash="cafef00d",
        cost_limit_usd=1.0,
        accumulated_cost_usd=0.0,
        dry_run=True,
        response_schema=ReformulatedQuery,
    )
    assert isinstance(response.parsed, ReformulatedQuery)
    assert response.parsed.query
    assert response.parsed.excluded_films == []
