from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, Literal, TypeVar

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from backend.llm import llm_harness
from backend.llm.types import LLMResponse
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

TResult = TypeVar("TResult")


class LLMAgent(ABC, Generic[TResult]):
    """Abstract base for a single-turn LLM agent.

    Subclasses declare their identity as class variables and implement two
    abstract methods; the common render → call → log → parse loop lives in
    ``run``.

    Class variables to define in each subclass:
        name:            Agent name; resolves the prompts directory.
        step_type:       Step identifier in LLM call logs (e.g. ``"intent_agent"``).
        model_tier:      Which model config to use: ``"strong"`` or ``"fast"``.
        template_name:   Jinja2 template filename (e.g. ``"intent_v10.j2"``).
        response_schema: Pydantic schema for structured output; ``None`` for plain text.
    """

    name: ClassVar[str]
    step_type: ClassVar[str]
    model_tier: ClassVar[Literal["strong", "fast"]]
    template_name: ClassVar[str]
    response_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(prompts_dir(self.name))), autoescape=False
        )

    @abstractmethod
    async def render_kwargs(self, **inputs: Any) -> dict[str, Any]:
        """Build Jinja2 template variables from agent-specific inputs.

        May perform I/O (e.g. DB lookups) when the prompt requires data not
        present in the caller's arguments.  Called by ``run`` before the
        harness call.

        Args:
            **inputs: Agent-specific keyword arguments, including the
                      standard trio (``conversation_id``, ``message_id``,
                      ``accumulated_cost``) merged in by ``run``.

        Returns:
            Dict passed directly to ``template.render(**kwargs)``.
        """

    @abstractmethod
    def build_result(self, resp: LLMResponse, **inputs: Any) -> TResult:
        """Construct the agent result from the LLM response.

        Called by ``run`` after the harness call.  Must be synchronous.

        Args:
            resp:     LLM response from the harness (``resp.content``,
                      ``resp.parsed``, ``resp.cost_usd``).
            **inputs: Same merged inputs passed to ``render_kwargs``,
                      including the standard trio.

        Returns:
            Agent-specific result dataclass.
        """

    async def run(
        self,
        *,
        conversation_id: uuid.UUID | str,
        message_id: uuid.UUID | str,
        accumulated_cost: float,
        run_id: str = "online",
        **inputs: Any,
    ) -> TResult:
        """Render the prompt, call the LLM harness, and build the result.

        The standard trio (``conversation_id``, ``message_id``,
        ``accumulated_cost``) is merged into ``inputs`` before calling
        ``render_kwargs`` and ``build_result`` so subclasses can access them
        without carrying separate parameters.

        Args:
            conversation_id:  Conversation UUID (or string) for logging.
            message_id:       Message UUID (or string) for logging.
            accumulated_cost: Running LLM cost this conversation.
            run_id:           Experiment run identifier (``"online"`` by
                              default; ``"offline"`` for the labeling agent's
                              batch pipeline).
            **inputs:         Agent-specific inputs forwarded to
                              ``render_kwargs`` and ``build_result``.

        Returns:
            Agent result as produced by ``build_result``.
        """
        ctx_inputs: dict[str, Any] = {
            **inputs,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "accumulated_cost": accumulated_cost,
        }

        cfg = get_settings()
        model = getattr(cfg.models, self.model_tier)

        kwargs = await self.render_kwargs(**ctx_inputs)
        prompt = self._env.get_template(self.template_name).render(**kwargs)
        log.debug("llm_prompt", extra={"template": self.template_name, "prompt": prompt})
        messages = [{"role": "user", "content": prompt}]

        resp = await llm_harness.call(
            run_id=run_id,
            conversation_id=str(conversation_id),
            message_id=str(message_id),
            config_hash=get_config_hash(),
            model_and_version=model.name,
            provider=model.provider,
            seed=model.seed,
            max_tokens=model.max_tokens,
            step_type=self.step_type,
            messages=messages,
            cost_limit_usd=cfg.conversation.cost_limit_usd,
            accumulated_cost_usd=accumulated_cost,
            dry_run=model.dry_run,
            response_schema=self.response_schema,
        )
        log.debug("llm_response", extra={"step_type": self.step_type, "content": resp.content})

        return self.build_result(resp, **ctx_inputs)
