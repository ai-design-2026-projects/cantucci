import openai
from backend.settings import get_env

# Cached async clients for each provider to avoid redundant construction.
_clients: dict[str, openai.AsyncOpenAI] = {}

_PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
}

_ALLOWED_PROVIDERS = set(_PROVIDER_BASE_URLS.keys())

def get_client(provider: str = "openai") -> openai.AsyncOpenAI:
    """
    Return the shared async client for *provider*, creating it on first call.
    Args:
        provider: API provider — ``"openai"`` (default) or ``"openrouter"``.
    Returns:
        A cached ``openai.AsyncOpenAI`` instance for the given provider.
    Raises:
        ValueError: If the required API key env var is not set.
    """
    if provider not in _ALLOWED_PROVIDERS:
        raise ValueError(
            f"Unsupported provider '{provider}'. Allowed providers: {', '.join(_ALLOWED_PROVIDERS)}"
        )
    
    # Return cached client if already created.
    if provider in _clients:
        return _clients[provider]
    env = get_env()
    
    # Construct and cache the client for this provider.
    if provider == "openrouter":
        if not env.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is not set. Add it to .env when using provider=openrouter."
            )
        _clients[provider] = openai.AsyncOpenAI(
            base_url=_PROVIDER_BASE_URLS["openrouter"],
            api_key=env.openrouter_api_key,
        )
    else:
        if not env.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Add it to .env when using provider=openai."
            )
        _clients[provider] = openai.AsyncOpenAI(api_key=env.openai_api_key)
    return _clients[provider]
