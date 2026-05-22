import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.settings import LOGS_DIR

_NOISY_THIRD_PARTY_LOGGERS = (
    "httpx",
    "httpcore",
    "huggingface_hub",
    "transformers",
    "sentence_transformers",
    "urllib3",
)

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

# Component name -> logger prefix. Each entry gets a dedicated file handler
# attached to the named logger. Records still propagate up to root so the
# terminal stream handler (and all.log) also see them.
_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("app", "backend.app"),
    ("routers", "backend.routers"),
    ("data_access", "backend.data_access"),
    ("agents", "backend.agents"),
    ("llm", "backend.llm.llm_harness"),
    ("auth", "auth"),
)

_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file before rotation
_FILE_BACKUP_COUNT = 5              # keep 5 rotated copies


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


class _PlainFormatter(logging.Formatter):
    """Plain (no-ANSI) key=value formatter for log files.

    Same shape as ``_PrettyFormatter`` but without escape codes and with a
    full date in the timestamp so files remain readable when read days later.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format *record* as a plaintext key=value line."""
        ts = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level = f"{record.levelname:<8}"
        logger_name = record.name
        msg = record.getMessage()

        extras = " ".join(
            f"{k}={_safe_str(v)}"
            for k, v in record.__dict__.items()
            if k not in _STDLIB_ATTRS and not k.startswith("_")
        )

        line = f"{ts}  {level}  {logger_name}  {msg}"
        if extras:
            line += f"  {extras}"
        if record.exc_info:
            line += f"\n{self.formatException(record.exc_info)}"
        return line


# Internal helper functions (not part of the public API)
def _safe_str(value: Any) -> str:
    """Return *value* as a str, falling back to repr() for non-strings."""
    return value if isinstance(value, str) else repr(value)


def _make_run_dir() -> Path:
    """Create and return a fresh ``logs/<utc_timestamp>/`` directory for this process."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = LOGS_DIR / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _update_latest_symlink(run_dir: Path) -> None:
    """Point ``logs/latest`` at *run_dir*. Best-effort; silently skipped on failure."""
    latest = LOGS_DIR / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(run_dir.name)
    except OSError:
        # Symlinks may not be permitted (Windows w/o dev-mode, locked-down FS).
        # The log files themselves still get written; only the convenience link is missing.
        pass


def _make_file_handler(path: Path) -> RotatingFileHandler:
    """Build a rotating DEBUG-level file handler with the plain formatter."""
    handler = RotatingFileHandler(
        path,
        maxBytes=_FILE_MAX_BYTES,
        backupCount=_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_PlainFormatter())
    return handler


# Public API
def configure_logging() -> None:
    """Configure the root logger, attach per-component file handlers, and route uvicorn.

    Reads:
        LOG_LEVEL — terminal logging level (default: INFO). File handlers are
        always at DEBUG regardless of this setting.

    Creates a fresh ``logs/<utc_timestamp>/`` directory and writes one file per
    component plus a catch-all ``all.log``. Updates ``logs/latest`` symlink.

    Safe to call multiple times (force=True is passed to basicConfig and any
    previously-attached file handlers on package loggers are cleared first).
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(_PrettyFormatter())
    stream_handler.setLevel(level)

    run_dir = _make_run_dir()
    _update_latest_symlink(run_dir)

    # Root: terminal at LOG_LEVEL + catch-all file at DEBUG. Root level must be DEBUG
    # so file handlers see DEBUG records even when the terminal handler filters them out.
    all_handler = _make_file_handler(run_dir / "all.log")
    logging.basicConfig(level=logging.DEBUG, handlers=[stream_handler, all_handler], force=True)

    # One dedicated file per component, attached to the package logger so every
    # child module (e.g. backend.cluster.tools.X) routes into the same file.
    for component, prefix in _COMPONENTS:
        pkg_log = logging.getLogger(prefix)
        for existing in list(pkg_log.handlers):
            if isinstance(existing, RotatingFileHandler):
                pkg_log.removeHandler(existing)
                existing.close()
        pkg_log.addHandler(_make_file_handler(run_dir / f"{component}.log"))
        pkg_log.setLevel(logging.DEBUG)
        pkg_log.propagate = True

    # Route uvicorn's loggers through our stream formatter so request/error logs match.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_log = logging.getLogger(name)
        uv_log.handlers = [stream_handler]
        uv_log.propagate = False

    for name in _NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def log_llm_call(
    logger: logging.Logger,
    *,
    run_id: str | UUID,
    conversation_id: str | UUID,
    message_id: str | UUID,
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

    This helper enforces the field set required by CLAUDE.md so individual
    callers cannot accidentally omit fields. All parameters are keyword-only
    to prevent positional mistakes.

    Args:
        logger:            The module-level logger of the calling module.
        run_id:            Identifier for the top-level experiment run.
        conversation_id:   Identifier for the current conversation.
        message_id:        Identifier for the message that triggered this call.
        seed:              RNG seed used for this call (from config).
        config_hash:       SHA-256 prefix of the YAML config file in effect.
        model_and_version: Full model string, e.g. ``"gpt-4o-2024-08-06"``.
        prompt_hash:       SHA-256 prefix of the rendered prompt file.
        step_type:         The agent step name (e.g. ``"intent_agent"``).
        input_tokens:      Prompt tokens consumed.
        output_tokens:     Completion tokens produced.
        latency_ms:        Wall-clock time for the LLM call in milliseconds.
    """
    logger.info(
        "llm_call",
        extra={
            "run_id": str(run_id),
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
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


