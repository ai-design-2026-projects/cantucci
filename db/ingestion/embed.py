"""Sentence-transformer embedding wrapper."""
import logging
from typing import TYPE_CHECKING

import numpy as np

from backend.settings import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)

# Implement a SINGLETON cache for loaded models to avoid redundant loading and memory usage
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
    model_name: str | None = None,
    expected_dim: int | None = None,
    batch_size: int = 256,
) -> np.ndarray:
    """Encode *texts* and return a float32 array with the configured dimension.

    Args:
        texts: One composite text string per movie.
        model_name: HuggingFace model identifier; defaults to YAML config.
        expected_dim: Embedding dimensionality; defaults to YAML config.
        batch_size: Encoding batch size.

    Returns:
        Float32 ndarray of shape (len(texts), expected_dim), L2-normalised.
    """
    representation = get_settings().representation
    resolved_model = model_name or representation.model
    resolved_dim = expected_dim or representation.embedding_dim
    model = _load(resolved_model)
    log.info("encoding", extra={"n": len(texts), "batch_size": batch_size, "model": resolved_model})

    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    if embeddings.shape != (len(texts), resolved_dim):
        raise ValueError(
            f"Unexpected embedding shape {embeddings.shape}; "
            f"expected ({len(texts)}, {resolved_dim}). "
            f"Check that '{resolved_model}' produces {resolved_dim}-dim vectors."
        )
    return embeddings.astype(np.float32)
