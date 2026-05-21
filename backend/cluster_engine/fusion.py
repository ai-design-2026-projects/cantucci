import logging

import numpy as np

log = logging.getLogger(__name__)


def fuse_embeddings(
    text_emb: np.ndarray,
    review_emb: np.ndarray | None,
    text_weight: float,
    review_weight: float,
) -> np.ndarray:
    """Produce a single fused, L2-normalized embedding from text and review vectors.

    When review_emb is None (no reviews available), returns text_emb unchanged.
    The fusion formula is: normalize(text_weight * text + review_weight * review).

    Args:
        text_emb:      1024-d L2-normalized float32 text embedding.
        review_emb:    1024-d L2-normalized float32 review embedding, or None.
        text_weight:   Scalar weight for the text embedding (e.g. 0.6).
        review_weight: Scalar weight for the review embedding (e.g. 0.4).

    Returns:
        1024-d L2-normalized float32 fused embedding.
    """
    if review_emb is None:
        return text_emb

    fused = text_weight * text_emb + review_weight * review_emb
    norm = np.linalg.norm(fused)
    if norm == 0.0:
        return text_emb
    return (fused / norm).astype(np.float32)


def fuse_batch(
    text_embeddings: np.ndarray,
    review_embeddings: np.ndarray | None,
    text_weight: float,
    review_weight: float,
) -> np.ndarray:
    """Fuse text and review embeddings for a full batch of movies.

    Where review_embeddings rows are all-zero (movies without reviews), the
    fused result falls back to the text embedding.

    Args:
        text_embeddings:   Float32 array of shape (n, 1024), L2-normalized.
        review_embeddings: Float32 array of shape (n, 1024) with zero rows for
                           movies lacking reviews, or None to skip fusion entirely.
        text_weight:       Scalar weight for text embeddings.
        review_weight:     Scalar weight for review embeddings.

    Returns:
        Float32 array of shape (n, 1024), row-wise L2-normalized.
    """
    if review_embeddings is None:
        return text_embeddings

    has_review = (np.abs(review_embeddings).sum(axis=1) > 0)
    fused = text_embeddings.copy()
    if has_review.any():
        mixed = text_weight * text_embeddings[has_review] + review_weight * review_embeddings[has_review]
        norms = np.linalg.norm(mixed, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        fused[has_review] = (mixed / norms).astype(np.float32)

    n_fused = int(has_review.sum())
    log.info("fuse_batch", extra={"n_total": len(text_embeddings), "n_fused": n_fused, "n_fallback": len(text_embeddings) - n_fused})
    return fused
