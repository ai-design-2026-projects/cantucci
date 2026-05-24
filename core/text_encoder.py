from __future__ import annotations
import logging
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from backend.settings import get_settings


log = logging.getLogger(__name__)

_cache: dict[str, "SentenceTransformer"] = {}


def _load(model_name: str) -> "SentenceTransformer":
    if model_name not in _cache:
        from sentence_transformers import SentenceTransformer
        device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info("loading embedding model", extra={"model": model_name, "device": device})
        model = SentenceTransformer(model_name, device=device)
        if device == "cuda":
            model.half()
            log.info("model cast to float16", extra={"model": model_name})
        _cache[model_name] = model
    return _cache[model_name]


def embed_texts(texts: list[str]) -> np.ndarray:
    """Encode texts using the configured model with no query prefix.

    Convenience wrapper for online concept-axis and prototype building.

    Args:
        texts: List of strings to embed.

    Returns:
        Float32 ndarray of shape (len(texts), embedding_dim), L2-normalized.
    """
    return encode_all(texts)


def preload_model() -> None:
    """Preload the configured embedding model into cache at startup.

    Call this during application startup to eliminate first-call latency.
    If the model is already cached, this is a no-op.
    """
    representation = get_settings().representation
    model_name = representation.model
    _ = _load(model_name)
    log.info("embedding model preloaded", extra={"model": model_name})


def encode_optional_texts(
    texts: list[str | None],
    *,
    batch_size: int = 256,
) -> np.ndarray:
    """Encode texts that may be absent, leaving missing rows as zero vectors.

    Rows where ``texts[i]`` is ``None``, ``NaN``, or blank are left as
    all-zero in the output. Zero rows are treated as "missing modality" by
    ``core.fusion.fuse_batch`` (BGE fusion) and are excluded from
    multi-modal distance matrices built by ``core.fusion.combined_distance_matrix``.

    Args:
        texts:      List of strings or ``None``/``NaN`` values, one per row.
        batch_size: Encoding batch size forwarded to ``encode_all``.

    Returns:
        Float32 ndarray of shape ``(len(texts), embedding_dim)``, L2-normalised
        for present rows, all-zero for absent rows.
    """
    representation = get_settings().representation
    dim = representation.embedding_dim
    out = np.zeros((len(texts), dim), dtype=np.float32)

    present_idx = [
        i for i, t in enumerate(texts)
        if isinstance(t, str) and t.strip()
    ]
    if not present_idx:
        return out

    present_texts = [texts[i] for i in present_idx]  # type: ignore[index]
    emb = encode_all(present_texts, batch_size=batch_size)
    for dest, src_row in zip(present_idx, emb):
        out[dest] = src_row
    return out


def encode_all(
    texts: list[str],
    *,
    model_name: str | None = None,
    expected_dim: int | None = None,
    batch_size: int = 256,
    query_prefix: str | None = None,
) -> np.ndarray:
    """Encode *texts* and return a float32 array with the configured dimension.
    Args:
        - texts: List of strings to embed. Could be composite_text or the user's query in the vector_search tool.
        - model_name: HuggingFace model identifier; defaults to YAML config.
        - expected_dim: Embedding dimensionality; defaults to YAML config.
        - batch_size: Encoding batch size.
        - query_prefix: Instruction prefix prepended to each text before encoding.
            For BGE models, pass "Represent this sentence for searching relevant passages: "
            when encoding user queries. Leave None for catalogue passages (composite_text).

    Returns:
        Float32 ndarray of shape (len(texts), expected_dim), L2-normalised.
    """
    representation = get_settings().representation
    resolved_model = model_name or representation.model
    resolved_dim = expected_dim or representation.embedding_dim
    model = _load(resolved_model)
    log.info("encoding", extra={"n": len(texts), "batch_size": batch_size, "model": resolved_model})

    prefixed = [f"{query_prefix}{t}" for t in texts] if query_prefix else texts
    with torch.no_grad():
        embeddings = model.encode(
            prefixed,
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
