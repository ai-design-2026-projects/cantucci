"""Sentence-transformer embedding wrapper."""
import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_EXPECTED_DIM = 384

_cache: dict[str, "SentenceTransformer"] = {}


def _load(model_name: str) -> "SentenceTransformer":
    if model_name not in _cache:
        from sentence_transformers import SentenceTransformer
        log.info("loading embedding model", extra={"model": model_name})
        _cache[model_name] = SentenceTransformer(model_name)
    return _cache[model_name]


def encode_all(
    texts: list[str],
    *,
    model_name: str = _DEFAULT_MODEL,
    batch_size: int = 256,
) -> np.ndarray:
    """Encode *texts* and return a float32 array of shape (N, 384).

    Args:
        texts: One composite text string per movie.
        model_name: HuggingFace model identifier (must produce 384-dim vectors).
        batch_size: Encoding batch size.

    Returns:
        Float32 ndarray of shape (len(texts), 384), L2-normalised.
    """
    model = _load(model_name)
    log.info("encoding", extra={"n": len(texts), "batch_size": batch_size, "model": model_name})

    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    if embeddings.shape != (len(texts), _EXPECTED_DIM):
        raise ValueError(
            f"Unexpected embedding shape {embeddings.shape}; "
            f"expected ({len(texts)}, {_EXPECTED_DIM}). "
            f"Check that '{model_name}' produces {_EXPECTED_DIM}-dim vectors."
        )
    return embeddings.astype(np.float32)
