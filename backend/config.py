"""
Central configuration loader.

All environment variables consumed by the application are read here so that
the rest of the codebase never calls os.environ directly.
"""

import os

from dotenv import load_dotenv


load_dotenv()


def database_url() -> str:
    """Return the Postgres connection string. Raises KeyError if unset."""
    return os.environ["DATABASE_URL"]


def log_level() -> str:
    """Return the log level string (default INFO)."""
    return os.environ.get("LOG_LEVEL", "INFO").upper()


def openai_api_key() -> str:
    """Return the OpenAI API key. Raises KeyError if OPENAI_API_KEY is unset."""
    return os.environ["OPENAI_API_KEY"]
