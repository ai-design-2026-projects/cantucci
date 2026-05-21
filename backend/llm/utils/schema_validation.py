"""JSON parse and Pydantic validation for structured LLM responses."""

import json
import logging

from pydantic import BaseModel, ValidationError

from backend.llm.exceptions import LLMParseError

log = logging.getLogger(__name__)


def validate_response(
    content: str,
    schema: type[BaseModel],
    step_type: str,
) -> BaseModel:
    """Parse *content* as JSON and validate it against *schema*.

    Raises ``LLMParseError`` (with the raw payload) on either a JSON decode
    failure or a Pydantic validation error.  Callers in the retry loop catch
    this and either continue or re-raise after exhausting attempts.

    Args:
        content:   Raw string returned by the model.
        schema:    Pydantic model to validate against.
        step_type: Name of the calling agent step, used in error messages.

    Returns:
        The validated Pydantic model instance.

    Raises:
        LLMParseError: If *content* cannot be decoded as JSON or fails schema validation.
    """
    try:
        return schema.model_validate_json(content)
    except (ValidationError, json.JSONDecodeError) as exc:
        log.debug(
            "llm_call schema validation failed",
            extra={"step_type": step_type, "error": str(exc)[:200]},
        )
        raise LLMParseError(step_type=step_type, raw=content) from exc
