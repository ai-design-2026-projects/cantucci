import logging
import numpy as np

log = logging.getLogger(__name__)


def fuse_batch(
    text_embeddings: np.ndarray,
    review_embeddings: np.ndarray | None,
    text_weight: float,
    review_weight: float,
    trailer_embeddings: np.ndarray | None = None,
    trailer_weight: float = 0.0,
) -> np.ndarray:
    """
    Fuse text, review, and trailer embeddings for a full batch of movies.
    For each row, only the modalities with a non-zero vector contribute to the
    weighted sum.
    Args:
        text_embeddings:    Float32 array of shape (n, dim), L2-normalized.
        review_embeddings:  Float32 array of shape (n, dim) with zero rows for
                            movies lacking reviews, or None to skip entirely.
        text_weight:        Scalar weight for text embeddings.
        review_weight:      Scalar weight for review embeddings.
        trailer_embeddings: Float32 array of shape (n, dim) with zero rows for
                            movies lacking trailers, or None to skip entirely.
        trailer_weight:     Scalar weight for trailer embeddings (0.0 disables
                            trailer fusion regardless of the array).
    Returns:
        Float32 array of shape (n, dim), row-wise L2-normalized.
    """
    n = len(text_embeddings)
    fused = text_embeddings.copy()

    has_review = (
        np.abs(review_embeddings).sum(axis=1) > 0
        if review_embeddings is not None
        else np.zeros(n, dtype=bool)
    )
    has_trailer = (
        np.abs(trailer_embeddings).sum(axis=1) > 0
        if trailer_embeddings is not None and trailer_weight > 0.0
        else np.zeros(n, dtype=bool)
    )

    rows_to_fuse = has_review | has_trailer
    if rows_to_fuse.any():
        idx = np.where(rows_to_fuse)[0]
        mixed = text_weight * text_embeddings[idx]
        active_weight = np.full(len(idx), text_weight, dtype=np.float64)

        if review_embeddings is not None:
            rev_mask = has_review[idx]
            if rev_mask.any():
                mixed[rev_mask] += review_weight * review_embeddings[idx][rev_mask]
                active_weight[rev_mask] += review_weight

        if trailer_embeddings is not None and trailer_weight > 0.0:
            trail_mask = has_trailer[idx]
            if trail_mask.any():
                mixed[trail_mask] += trailer_weight * trailer_embeddings[idx][trail_mask]
                active_weight[trail_mask] += trailer_weight

        mixed = mixed / active_weight[:, np.newaxis]
        norms = np.linalg.norm(mixed, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        fused[idx] = (mixed / norms).astype(np.float32)

    n_review = int(has_review.sum())
    n_trailer = int(has_trailer.sum())
    log.info(
        "fuse_batch",
        extra={
            "n_total": n,
            "n_with_review": n_review,
            "n_with_trailer": n_trailer,
            "n_text_only": n - int(rows_to_fuse.sum()),
        },
    )
    return fused
