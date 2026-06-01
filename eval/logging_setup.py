"""Eval-specific logging configuration.

Extends the backend's ``configure_logging()`` with dedicated per-component
file handlers under ``logs/<ts>/eval/`` — the same timestamped run directory
that the backend logging already creates. Call this after
``configure_logging()`` in every eval entry point.

Files written (inside the current run dir resolved via ``logs/latest``):
    eval/all.log      — every eval record (DEBUG+)
    eval/oracle.log   — eval.oracle.*
    eval/judge.log    — eval.judge.*
    eval/builder.log  — eval.builder.*
    eval/session.log  — eval.runtime.*
    eval/llm.log      — backend.llm.llm_harness (LLM calls made from eval)
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.settings import LOGS_DIR

_FILE_MAX_BYTES = 10 * 1024 * 1024
_FILE_BACKUP_COUNT = 5

_EVAL_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("oracle", "eval.oracle"),
    ("judge", "eval.judge"),
    ("builder", "eval.builder"),
    ("session", "eval.runtime"),
)

_STDLIB_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class _PlainFormatter(logging.Formatter):
    """Plain key=value formatter for eval log files (no ANSI codes)."""

    def format(self, record: logging.LogRecord) -> str:
        """Format *record* as a plaintext key=value line."""
        ts = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level = f"{record.levelname:<8}"
        extras = " ".join(
            f"{k}={_safe_str(v)}"
            for k, v in record.__dict__.items()
            if k not in _STDLIB_ATTRS and not k.startswith("_")
        )
        line = f"{ts}  {level}  {record.name}  {record.getMessage()}"
        if extras:
            line += f"  {extras}"
        if record.exc_info:
            line += f"\n{self.formatException(record.exc_info)}"
        return line


def _safe_str(value: object) -> str:
    return value if isinstance(value, str) else repr(value)


def _make_file_handler(path: Path) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path,
        maxBytes=_FILE_MAX_BYTES,
        backupCount=_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_PlainFormatter())
    return handler


def configure_eval_logging() -> None:
    """Attach per-component eval file handlers inside the current run's ``eval/`` subdir.

    Resolves the current run directory by following the ``logs/latest`` symlink
    that ``configure_logging()`` creates. Creates ``logs/<ts>/eval/`` and writes
    one file per component plus a catch-all ``all.log``.

    Safe to call multiple times — existing ``RotatingFileHandler``s on the
    target loggers are removed before new ones are attached.

    Must be called after ``backend.logging_setup.configure_logging()``.
    """
    latest = LOGS_DIR / "latest"
    if latest.is_symlink():
        run_dir = (LOGS_DIR / latest.readlink()).resolve()
    else:
        run_dir = LOGS_DIR

    eval_dir = run_dir / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.addHandler(_make_file_handler(eval_dir / "all.log"))

    for component, prefix in _EVAL_COMPONENTS:
        pkg_log = logging.getLogger(prefix)
        for h in list(pkg_log.handlers):
            if isinstance(h, RotatingFileHandler):
                pkg_log.removeHandler(h)
                h.close()
        pkg_log.addHandler(_make_file_handler(eval_dir / f"{component}.log"))
        pkg_log.setLevel(logging.DEBUG)
        pkg_log.propagate = True

    llm_log = logging.getLogger("backend.llm.llm_harness")
    llm_log.addHandler(_make_file_handler(eval_dir / "llm.log"))
    llm_log.setLevel(logging.DEBUG)
    llm_log.propagate = True
