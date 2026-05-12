"""
Application-wide logging configuration.

Call configure_logging() exactly once at process startup (entry points, CLI
scripts, test conftest). All modules obtain their logger via:

    log = logging.getLogger(__name__)

Never use the root logger directly.
"""

import logging
import logging.config

from src.config import log_level


def configure_logging() -> None:
    """Configure JSON-line structured logging for the whole process."""
    level = log_level()

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "logging.Formatter",
                # Single-line JSON format; structured fields can be added via
                # the 'extra' kwarg on log calls.
                "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
            }
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            }
        },
        "root": {
            "level": level,
            "handlers": ["stdout"],
        },
    })
