from __future__ import annotations

import logging

import numpy as np

from backend.settings import get_settings
from core.image_encoder import encode_images
from dataset.embed.trailer_fetch import fetch_frames

log = logging.getLogger(__name__)


def _encode_one(youtube_key: str, n_frames: int, batch_size: int) -> np.ndarray:
    """Fetch frames for one movie and return a single L2-normalized 1024-d vector."""
    images = fetch_frames(youtube_key, n_frames=n_frames)
    frame_feats = encode_images(images, batch_size=batch_size)
    pooled = frame_feats.mean(axis=0)
    norm = float(np.linalg.norm(pooled))
    pooled = pooled / max(norm, 1e-12)
    return pooled.astype(np.float32)


def encode_trailers(
    movie_keys: list[tuple[int, str | None]],
    *,
    n_frames: int = 16,
    batch_size: int = 16,
) -> np.ndarray:
    """Embed trailers for a batch of movies into a single (n, dim) float32 array.

    Each movie's trailer is downloaded, ``n_frames`` evenly-spaced frames are
    extracted, each frame is encoded by ``core.image_encoder.encode_images``,
    the per-frame embeddings are mean-pooled and L2-normalized. Rows for
    movies with no ``youtube_key`` (None) or whose trailer fetch fails end up
    as all-zero — this matches the "missing modality" semantics expected by
    ``core.fusion.fuse_batch``.

    Args:
        movie_keys: List of ``(movie_id, youtube_key)`` pairs. ``movie_id`` is
            used only for logging; row alignment follows list order.
        n_frames:   Number of frames to sample per trailer.
        batch_size: CLIP image-encoder batch size for the per-movie frame batch.

    Returns:
        Float32 ndarray of shape ``(len(movie_keys), embedding_dim)``, where
        ``embedding_dim`` is taken from the active YAML config (must equal the
        CLIP backbone's native output dim — 1024 for ViT-H/14).
    """
    dim = get_settings().representation.embedding_dim
    out = np.zeros((len(movie_keys), dim), dtype=np.float32)

    n_done = 0
    n_skipped = 0
    n_failed = 0
    for i, (movie_id, key) in enumerate(movie_keys):
        if not key:
            n_skipped += 1
            continue
        try:
            vec = _encode_one(key, n_frames=n_frames, batch_size=batch_size)
        except Exception as exc:
            log.warning(
                "trailer_encode_failed",
                extra={"movie_id": movie_id, "youtube_key": key, "error": str(exc)},
            )
            n_failed += 1
            continue
        if vec.shape != (dim,):
            raise RuntimeError(
                f"CLIP output dim {vec.shape[0]} does not match configured "
                f"embedding_dim {dim}. Pick a CLIP backbone whose native output "
                f"matches configs/default.yaml:representation.embedding_dim."
            )
        out[i] = vec
        n_done += 1

    log.info(
        "encode_trailers_complete",
        extra={
            "n_total": len(movie_keys),
            "n_encoded": n_done,
            "n_skipped_no_key": n_skipped,
            "n_failed": n_failed,
        },
    )
    return out
