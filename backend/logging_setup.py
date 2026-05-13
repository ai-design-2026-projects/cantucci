"""Logging setup for the CinePal backend.

Call configure_logging() once at application startup (in app.py lifespan).
Every other module then does:
    log = logging.getLogger(__name__)

Output: ANSI-coloured key=value lines (always). Level controlled by LOG_LEVEL (default: INFO).

Uvicorn's own loggers (uvicorn, uvicorn.error, uvicorn.access) are routed
through the same formatter so all backend output has a consistent shape.

LLM calls:
    from backend.logging_setup import log_llm_call
    log_llm_call(log, run_id=..., session_id=..., ...)
Emits a structured INFO record containing the exact field set mandated by CLAUDE.md.
"""

import logging
import os
from typing import Any
from uuid import UUID

# ANSI escape codes for coloured terminal output. Supported by most modern terminals.
_RESET = "\033[0m"
_DIM = "\033[2m"

_LEVEL_COLOURS = {
    "DEBUG": "\033[36m",     # cyan
    "INFO": "\033[32m",      # green
    "WARNING": "\033[33m",   # yellow
    "ERROR": "\033[31m",     # red
    "CRITICAL": "\033[35m",  # magenta
}

# Attrs that exist on every LogRecord so we don't re-emit them as extras.
_STDLIB_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


# Formatter classes must inherit from logging.Formatter and implement format(record).
class _PrettyFormatter(logging.Formatter):
    """ANSI-coloured, human-readable formatter for local development.

    Format per line:
        <dim timestamp>  <coloured LEVEL>  message  key=value …

    Non-string extra values are rendered with repr() so the line is always
    safe to print regardless of value type.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format *record* as a coloured key=value line.

        Args:
            record: The log record to format.

        Returns:
            A human-readable ANSI string.
        """
        ts = f"{_DIM}{self.formatTime(record, '%H:%M:%S')}{_RESET}"
        colour = _LEVEL_COLOURS.get(record.levelname, "")
        level = f"{colour}{record.levelname:<8}{_RESET}"
        msg = record.getMessage()

        extras = " ".join(
            f"{_DIM}{k}{_RESET}={_safe_str(v)}"
            for k, v in record.__dict__.items()
            if k not in _STDLIB_ATTRS and not k.startswith("_")
        )

        line = f"{ts}  {level}  {msg}"
        if extras:
            line += f"\n\t\t{extras}"
        if record.exc_info:
            line += f"\n{self.formatException(record.exc_info)}"
        return line


# Internal helper functions (not part of the public API)
def _safe_str(value: Any) -> str:
    """Return *value* as a str, falling back to repr() for non-strings."""
    return value if isinstance(value, str) else repr(value)


# Public API
def configure_logging() -> None:
    """Configure the root logger and route uvicorn loggers through the same handler.

    Reads:
        LOG_LEVEL — root logging level (default: INFO).

    Always uses the ANSI pretty formatter. Safe to call multiple times
    (force=True is passed to basicConfig).
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter: logging.Formatter = _PrettyFormatter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=[handler], force=True)

    # Route uvicorn's loggers through our formatter so request/error logs match.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_log = logging.getLogger(name)
        uv_log.handlers = [handler]
        uv_log.propagate = False


def log_llm_call(
    logger: logging.Logger,
    *,
    run_id: str | UUID,
    session_id: str | UUID,
    turn_id: str | UUID,
    seed: int,
    config_hash: str,
    model_and_version: str,
    prompt_hash: str,
    step_type: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
) -> None:
    """Emit a structured INFO record capturing every required LLM call field.

    This helper enforces the field set mandated by CLAUDE.md so individual
    callers cannot accidentally omit fields. All parameters are keyword-only
    to prevent positional mistakes.

    Args:
        logger:           The module-level logger of the calling module.
        run_id:           Identifier for the top-level experiment run.
        session_id:       Identifier for the current conversation session.
        turn_id:          Identifier for the turn that triggered this call.
        seed:             RNG seed used for this call (from session config).
        config_hash:      SHA-256 prefix of the YAML config file in effect.
        model_and_version: Full model string, e.g. ``"gpt-4o-2024-08-06"``.
        prompt_hash:      SHA-256 prefix of the rendered prompt file.
        step_type:        The ``f_*`` function or agent step (e.g. ``"f_output"``).
        input_tokens:     Prompt tokens consumed.
        output_tokens:    Completion tokens produced.
        latency_ms:       Wall-clock time for the LLM call in milliseconds.
    """
    logger.info(
        "llm_call",
        extra={
            "run_id": str(run_id),
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "seed": seed,
            "config_hash": config_hash,
            "model_and_version": model_and_version,
            "prompt_hash": prompt_hash,
            "step_type": step_type,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
        },
    )
