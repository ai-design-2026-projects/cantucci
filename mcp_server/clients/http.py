import httpx


class BackendError(Exception):
    """Raised when the CinePal backend returns a non-2xx response.

    Attributes:
        status_code: HTTP status code returned by the backend.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(f"Backend error {status_code}: {detail}")


class BaseClient:
    """Base HTTP client that holds the shared httpx.AsyncClient.

    All domain clients inherit from this class and share the same
    underlying connection pool. The ``httpx.AsyncClient`` is injected
    from the composition root (``server.py``) so a single pool is reused
    across all domains.

    Attributes:
        _http: The shared async HTTP client.
    """

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    def _check(self, response: httpx.Response) -> httpx.Response:
        """Raise ``BackendError`` for non-2xx responses.

        Args:
            response: The httpx response to check.

        Returns:
            The same response if it is 2xx.

        Raises:
            BackendError: If the response status code indicates an error.
        """
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise BackendError(response.status_code, str(detail))
        return response
