import logging
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from backend.logging_setup import log_llm_call
from backend.settings import PROJECT_ROOT
from backend.llm.types import LLMResponse
from backend.llm.utils.schema_validation import validate_response

log = logging.getLogger(__name__)

_DRY_RUN_FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "dry_run"


def dry_run_response(
    *,
    step_type: str,
    response_schema: type[BaseModel] | None,
    run_id: str | UUID,
    session_id: str | UUID,
    turn_id: str | UUID,
    seed: int,
    config_hash: str,
    model_and_version: str,
    prompt_hash: str,
) -> LLMResponse:
    """Load a fixture file and return it as an LLMResponse without an API call.

    The fixture must be a JSON file at
    ``tests/fixtures/dry_run/{step_type}.json``.  If ``response_schema`` is
    provided, the fixture content is also validated against the schema so a
    broken fixture is caught during tests rather than at runtime.

    Args:
        step_type:        Name of the calling agent step; selects the fixture file.
        response_schema:  Optional Pydantic model to validate the fixture against.
        run_id:           Experiment run identifier for logging.
        session_id:       Conversation session identifier for logging.
        turn_id:          Turn identifier for logging.
        seed:             RNG seed from session config.
        config_hash:      SHA-256 prefix of the YAML config in effect.
        model_and_version: Full model string from config.
        prompt_hash:      SHA-256 prefix of the rendered prompt.

    Returns:
        An ``LLMResponse`` with zero token counts and zero latency.

    Raises:
        FileNotFoundError: If the fixture file for *step_type* does not exist.
        LLMParseError:     If *response_schema* is set and the fixture fails validation.
    """
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
    parsed = validate_response(content, response_schema, step_type) if response_schema else None
    return LLMResponse(
        content=content,
        input_tokens=0,
        output_tokens=0,
        latency_ms=0.0,
        parsed=parsed,
    )
