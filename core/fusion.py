import logging
import numpy as np

log = logging.getLogger(__name__)


def fuse_batch(
    text_embeddings: np.ndarray,
    review_embeddings: np.ndarray | None,
    text_weight: float,
    review_weight: float,
) -> np.ndarray:
    """Fuse text and review embeddings for a batch of movies (BGE space only).

    Both inputs live in the same BGE embedding space, so weighted averaging is
    geometrically valid. For cross-space combination (e.g. BGE text + CLIP
    trailer) use ``combined_distance_matrix`` instead.

    For each row, only the modalities with a non-zero vector contribute to
    the weighted sum. Rows with no review are text-only.

    Args:
        text_embeddings:   Float32 array of shape (n, dim), L2-normalized.
        review_embeddings: Float32 array of shape (n, dim) with zero rows for
                           movies lacking reviews, or None to use text only.
        text_weight:       Scalar weight for text embeddings.
        review_weight:     Scalar weight for review embeddings.

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

    if has_review.any():
        idx = np.where(has_review)[0]
        mixed = text_weight * text_embeddings[idx]
        active_weight = np.full(len(idx), text_weight + review_weight, dtype=np.float64)

        if review_embeddings is not None:
            mixed += review_weight * review_embeddings[idx]

        mixed = mixed / active_weight[:, np.newaxis]
        norms = np.linalg.norm(mixed, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        fused[idx] = (mixed / norms).astype(np.float32)

    log.info(
        "fuse_batch",
        extra={
            "n_total": n,
            "n_with_review": int(has_review.sum()),
            "n_text_only": n - int(has_review.sum()),
        },
    )
    return fused


def combined_distance_matrix(
    embeddings_by_modality: dict[str, np.ndarray],
    weights: dict[str, float],
) -> np.ndarray:
    """Build a combined pairwise distance matrix across multiple embedding spaces.

    Each modality contributes a cosine distance matrix; these are weight-summed
    to produce one composite (n, n) matrix. This is the correct way to mix
    embeddings from incompatible spaces (e.g. BGE text and CLIP visual) — it
    operates at the distance level rather than averaging vectors across spaces.

    Args:
        embeddings_by_modality: Dict mapping modality name → float32 (n, dim)
                                array of L2-normalised embeddings. All arrays
                                must have the same number of rows (n).
        weights:                Dict mapping modality name → non-negative scalar
                                weight. Modalities present in
                                ``embeddings_by_modality`` but absent from
                                ``weights`` default to weight 1.0. Weights are
                                normalised to sum to 1 internally.

    Returns:
        Float32 symmetric (n, n) distance matrix with values in [0, 2].
        Suitable as input to HDBSCAN with ``metric="precomputed"``.

    Raises:
        ValueError: If ``embeddings_by_modality`` is empty or arrays disagree
                    on the number of rows.
    """
    if not embeddings_by_modality:
        raise ValueError("embeddings_by_modality must not be empty")

    sizes = {name: arr.shape[0] for name, arr in embeddings_by_modality.items()}
    if len(set(sizes.values())) > 1:
        raise ValueError(f"All modality arrays must have the same number of rows; got {sizes}")

    n = next(iter(sizes.values()))
    combined = np.zeros((n, n), dtype=np.float64)
    total_weight = 0.0

    for name, emb in embeddings_by_modality.items():
        w = float(weights.get(name, 1.0))
        if w <= 0.0:
            continue
        sim = emb @ emb.T
        np.clip(sim, -1.0, 1.0, out=sim)
        dist = 1.0 - sim
        combined += w * dist
        total_weight += w

    if total_weight == 0.0:
        raise ValueError("All modality weights are zero or non-positive")

    combined /= total_weight

    log.info(
        "combined_distance_matrix",
        extra={"n": n, "modalities": list(embeddings_by_modality.keys()), "weights": weights},
    )
    return combined.astype(np.float32)
