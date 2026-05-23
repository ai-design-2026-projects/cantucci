from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
from tqdm.auto import tqdm

from backend.settings import get_settings
from core.image_encoder import encode_images
# dataset.fetch.trailer is an external-source fetcher; it stays in dataset/fetch/
# alongside tmdb.py. This is the only core → dataset dependency — accepted
# because fetch_frames is the sole I/O boundary for YouTube and belongs there.
from dataset.fetch.trailer import fetch_frames

log = logging.getLogger(__name__)


def _encode_one(
    youtube_key: str,
    n_frames: int,
    batch_size: int,
) -> np.ndarray:
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
    as all-zero — they are excluded from multi-modal distance matrices when
    using ``core.fusion.combined_distance_matrix``.

    Args:
        movie_keys: List of ``(movie_id, youtube_key)`` pairs. ``movie_id``
                    is used only for logging; row alignment follows list order.
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
    with tqdm(total=len(movie_keys), desc="trailer embed", unit="movie") as bar:
        for i, (movie_id, key) in enumerate(movie_keys):
            if not key:
                n_skipped += 1
                bar.update(1)
                continue
            try:
                vec = _encode_one(key, n_frames, batch_size)
            except Exception as exc:
                log.warning(
                    "trailer_encode_failed",
                    extra={"movie_id": movie_id, "youtube_key": key, "error": str(exc)},
                )
                n_failed += 1
                bar.update(1)
                continue
            if vec.shape != (dim,):
                raise RuntimeError(
                    f"CLIP output dim {vec.shape[0]} does not match configured "
                    f"embedding_dim {dim}. Pick a CLIP backbone whose native output "
                    f"matches configs/default.yaml:representation.embedding_dim."
                )
            out[i] = vec
            n_done += 1
            bar.set_postfix(ok=n_done, skip=n_skipped, fail=n_failed)
            bar.update(1)

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


def encode_trailers_sharded(
    movie_keys: list[tuple[int, str | None]],
    shard_dir: Path,
    *,
    shard_size: int = 50,
    n_frames: int = 16,
    batch_size: int = 16,
    max_shards_per_run: int | None = None,
) -> tuple[np.ndarray, bool]:
    """Resumable, sharded version of encode_trailers.

    Splits ``movie_keys`` into contiguous shards of ``shard_size`` entries.
    Each shard is persisted as ``shard_dir / shard_{idx:05d}.npz`` containing
    arrays ``movie_ids`` (int64) and ``vectors`` (float32). Existing shards are
    loaded and validated; missing shards are embedded and saved atomically.
    When ``max_shards_per_run`` newly embedded shards have been produced the
    function returns early so that partial progress is visible in the caller.

    Designed to be called repeatedly across Colab sessions with the same
    ``shard_dir`` backed by Google Drive. Each call resumes from where the
    previous left off.

    Args:
        movie_keys:        List of ``(movie_id, youtube_key)`` pairs aligned to
                           the split's row order.
        shard_dir:         Directory in which shard ``.npz`` files are written
                           and read. Must already exist.
        shard_size:        Number of movies per shard.
        n_frames:          Frames sampled per trailer (forwarded to
                           ``_encode_one``).
        batch_size:        CLIP encoder batch size (forwarded to ``_encode_one``).
        max_shards_per_run: If set, stop after embedding this many new shards
                            (existing shards are loaded but not counted). Pass
                            ``None`` to process everything in one call.

    Returns:
        ``(out, complete)`` where ``out`` is a ``(n, dim)`` float32 array with
        zero rows for any still-missing shards, and ``complete`` is ``True``
        iff every shard was present or produced by this call.

    Raises:
        RuntimeError: If a loaded shard's stored ``movie_ids`` do not match
                      the expected slice — indicates the snapshot changed
                      between runs.
        RuntimeError: If CLIP output dim does not match the configured
                      ``embedding_dim``.
    """
    dim = get_settings().representation.embedding_dim
    n_total = len(movie_keys)
    out = np.zeros((n_total, dim), dtype=np.float32)

    n_shards = (n_total + shard_size - 1) // shard_size
    new_shards_embedded = 0
    all_complete = True

    for shard_idx in range(n_shards):
        start = shard_idx * shard_size
        end = min(start + shard_size, n_total)
        shard_keys = movie_keys[start:end]
        expected_ids = np.array([mid for mid, _ in shard_keys], dtype=np.int64)

        shard_path = shard_dir / f"shard_{shard_idx:05d}.npz"

        if shard_path.exists():
            data = np.load(shard_path)
            stored_ids = data["movie_ids"]
            if not np.array_equal(stored_ids, expected_ids):
                raise RuntimeError(
                    f"Shard {shard_path} contains movie_ids that do not match "
                    f"the current snapshot split. The snapshot or split seed may "
                    f"have changed between runs. Delete the shard directory and "
                    f"restart embedding from scratch."
                )
            out[start:end] = data["vectors"]
            log.info(
                "shard_skipped_existing",
                extra={"shard_idx": shard_idx, "n_shards": n_shards, "shard_path": str(shard_path)},
            )
            continue

        if max_shards_per_run is not None and new_shards_embedded >= max_shards_per_run:
            all_complete = False
            continue

        log.info(
            "shard_started",
            extra={"shard_idx": shard_idx, "n_shards": n_shards, "movies": end - start},
        )
        vectors = np.zeros((end - start, dim), dtype=np.float32)
        n_done = 0
        n_failed = 0
        with tqdm(
            total=end - start,
            desc=f"shard {shard_idx}/{n_shards - 1}",
            unit="movie",
            leave=False,
        ) as bar:
            for j, (movie_id, key) in enumerate(shard_keys):
                if not key:
                    bar.update(1)
                    continue
                try:
                    vec = _encode_one(key, n_frames, batch_size)
                except Exception as exc:
                    log.warning(
                        "trailer_encode_failed",
                        extra={"movie_id": movie_id, "youtube_key": key, "error": str(exc)},
                    )
                    n_failed += 1
                    bar.update(1)
                    continue
                if vec.shape != (dim,):
                    raise RuntimeError(
                        f"CLIP output dim {vec.shape[0]} does not match configured "
                        f"embedding_dim {dim}."
                    )
                vectors[j] = vec
                n_done += 1
                bar.set_postfix(ok=n_done, fail=n_failed)
                bar.update(1)

        tmp_path = shard_path.with_suffix(".tmp.npz")
        np.savez(tmp_path, movie_ids=expected_ids, vectors=vectors)
        os.replace(tmp_path, shard_path)

        out[start:end] = vectors
        new_shards_embedded += 1
        log.info(
            "shard_completed",
            extra={
                "shard_idx": shard_idx,
                "n_shards": n_shards,
                "n_encoded": n_done,
                "n_failed": n_failed,
                "shard_path": str(shard_path),
            },
        )

    log.info(
        "encode_trailers_sharded_summary",
        extra={
            "n_total": n_total,
            "n_shards": n_shards,
            "new_shards_embedded": new_shards_embedded,
            "complete": all_complete,
        },
    )
    return out, all_complete
