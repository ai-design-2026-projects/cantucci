from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image

log = logging.getLogger(__name__)

_TMDB_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"


def fetch_poster(poster_path: str | None, *, timeout: float = 10.0) -> Image.Image | None:
    """Fetch a TMDB poster as a PIL RGB image.

    poster_path is the TMDB stub stored in the catalogue (e.g. ``"/abc.jpg"``).
    Returns ``None`` if ``poster_path`` is falsy or the HTTP fetch fails, so
    callers can treat ``None`` as "no poster available" without raising.

    Args:
        poster_path: TMDB poster path stub. If ``None`` or empty, returns
                     ``None`` immediately.
        timeout:     HTTP request timeout in seconds.

    Returns:
        RGB PIL image, or ``None`` if the poster cannot be fetched.
    """
    import httpx

    if not poster_path:
        return None

    url = f"{_TMDB_POSTER_BASE_URL}{poster_path}"
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        return Image.open(BytesIO(response.content)).convert("RGB")
    except Exception as exc:
        log.warning(
            "poster_fetch_failed",
            extra={"poster_path": poster_path, "url": url, "error": str(exc)},
        )
        return None
