from pydantic_settings import BaseSettings


class McpSettings(BaseSettings):
    """Settings for the CinePal MCP server.

    Attributes:
        backend_url: Base URL of the CinePal FastAPI backend.
        timeout:     HTTP request timeout in seconds.
    """

    backend_url: str = "http://localhost:8000"
    timeout: float = 30.0

    model_config = {"env_prefix": "CINEPAL_MCP_"}


_settings: McpSettings | None = None


def get_settings() -> McpSettings:
    """Return the singleton MCP settings instance."""
    global _settings
    if _settings is None:
        _settings = McpSettings()
    return _settings
