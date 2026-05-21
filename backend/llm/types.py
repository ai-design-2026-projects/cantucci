from dataclasses import dataclass, field
from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Result of a single LLM call, returned by ``backend.llm_harness.call()``.

    Attributes:
        content:       Raw text produced by the model.
        input_tokens:  Prompt tokens consumed (billed separately from output).
        output_tokens: Completion tokens produced.
        latency_ms:    Wall-clock duration of the API call in milliseconds.
        cost_usd:      Estimated USD cost based on token counts and model pricing.
        parsed:        Pydantic-validated payload when ``response_schema`` was set
                       on the call; ``None`` when the caller asked for raw text only.
    """
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float = field(default=0.0)
    parsed: BaseModel | None = field(default=None)
