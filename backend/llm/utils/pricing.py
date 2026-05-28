import logging

log = logging.getLogger(__name__)

# USD per million tokens for known model families.  Models are matched by
# prefix so version suffixes are tolerated (e.g. "gpt-4o-mini-2024-07-18"
# matches "gpt-4o-mini"). OpenRouter-prefixed model strings (e.g.
# "openai/gpt-4o-mini") must be placed before their bare equivalents to
# prevent shadowing.
_COST_PER_M: dict[str, dict[str, float]] = {
    # OpenRouter free tier (development/testing)
    "openrouter/owl-alpha": {"input": 0.0, "output": 0.0},
    # OpenRouter-prefixed Google family
    "google/gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "google/gemini-flash-1.5": {"input": 0.075, "output": 0.30},
    # OpenRouter-prefixed Anthropic family (must precede bare prefixes)
    "anthropic/claude-opus": {"input": 15.0, "output": 75.0},
    "anthropic/claude-sonnet": {"input": 3.0, "output": 15.0},
    "anthropic/claude-haiku": {"input": 0.80, "output": 4.0},
    # OpenRouter-prefixed GPT family (must precede bare prefixes)
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    # Direct OpenAI bare prefixes (legacy / direct-API usage)
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "claude-opus": {"input": 15.0, "output": 75.0},
    "claude-sonnet": {"input": 3.0, "output": 15.0},
    "claude-haiku": {"input": 0.80, "output": 4.0},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Estimate USD cost from token counts using the pricing table.
    Args:
        model:         Full model string, e.g. ``"gpt-4o-2024-08-06"``.
        input_tokens:  Prompt tokens consumed.
        output_tokens: Completion tokens produced.
    Returns:
        Estimated cost in USD, or ``0.0`` if the model is not in the table.
    """
    for prefix, rates in _COST_PER_M.items():
        if model.startswith(prefix):
            return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    log.warning("unknown model for cost estimation, charging 0", extra={"model": model})
    return 0.0
