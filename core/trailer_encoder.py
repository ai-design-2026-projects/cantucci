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
from dataset.fetch.poster import fetch_poster

log = logging.getLogger(__name__)


def _encode_one(
    youtube_key: str,
    n_frames: int,
    batch_size: int,
) -> np.ndarray:
    """Fetch frames for one movie and return a single L2-normalized 1024-d vector.

    Args:
        youtube_key: YouTube video ID for the trailer.
        n_frames:    Number of evenly-spaced frames to sample.
        batch_size:  CLIP image-encoder batch size.

    Returns:
        L2-normalized float32 vector of shape ``(embedding_dim,)``.

    Raises:
        RuntimeError: If the trailer yields no frames or the CLIP output dim
                      does not match the configured embedding_dim.
    """
    images = fetch_frames(youtube_key, n_frames=n_frames)
    if not images:
        raise RuntimeError(
            f"fetch_frames returned no frames for youtube_key={youtube_key!r}"
        )
    frame_feats = encode_images(images, batch_size=batch_size)
    pooled = frame_feats.mean(axis=0)
    norm = float(np.linalg.norm(pooled))
    pooled = pooled / max(norm, 1e-12)
    return pooled.astype(np.float32)


def _encode_poster_one(poster_path: str | None) -> np.ndarray | None:
    """Encode a single TMDB poster image via CLIP.

    Fetches the poster by HTTP and encodes it with ``core.image_encoder.encode_images``.
    Returns ``None`` if the poster is unavailable or the fetch fails, so that
    the caller can fall through to a zero row without raising.

    Args:
        poster_path: TMDB poster path stub (e.g. ``"/abc.jpg"``), or ``None``.

    Returns:
        L2-normalized float32 vector of shape ``(1024,)``, or ``None``.
    """
    img = fetch_poster(poster_path)
    if img is None:
        return None
    feats = encode_images([img])
    if feats.shape[0] == 0:
        return None
    return feats[0].astype(np.float32)


def encode_trailers(
    movie_keys: list[tuple[int, str | None, str | None]],
    *,
    n_frames: int = 16,
    batch_size: int = 16,
) -> np.ndarray:
    """Embed trailers (or poster fallback) for a batch of movies.

    Each movie's trailer is downloaded, ``n_frames`` evenly-spaced frames are
    extracted, each frame is encoded by ``core.image_encoder.encode_images``,
    the per-frame embeddings are mean-pooled and L2-normalized.

    If a movie has no ``youtube_key`` or its trailer fetch fails, the poster
    image (``poster_path``) is encoded instead via ``_encode_poster_one``.
    Rows where both trailer and poster are unavailable end up as all-zero.

    Args:
        movie_keys: List of ``(movie_id, youtube_key, poster_path)`` triples.
                    ``movie_id`` is used only for logging; row alignment follows
                    list order. Either of ``youtube_key`` or ``poster_path`` may
                    be ``None``.
        n_frames:   Number of frames to sample per trailer.
        batch_size: CLIP image-encoder batch size for the per-movie frame batch.

    Returns:
        Float32 ndarray of shape ``(len(movie_keys), embedding_dim)``.
    """
    dim = get_settings().representation.embedding_dim
    out = np.zeros((len(movie_keys), dim), dtype=np.float32)

    n_done = 0
    n_poster_fallback = 0
    n_skipped = 0
    n_failed = 0
    with tqdm(total=len(movie_keys), desc="trailer embed", unit="movie") as bar:
        for i, (movie_id, key, poster_path) in enumerate(movie_keys):
            vec: np.ndarray | None = None

            if key:
                try:
                    vec = _encode_one(key, n_frames, batch_size)
                except Exception as exc:
                    log.warning(
                        "trailer_encode_failed",
                        extra={"movie_id": movie_id, "youtube_key": key, "error": str(exc)},
                    )

            if vec is None:
                vec = _encode_poster_one(poster_path)
                if vec is not None:
                    n_poster_fallback += 1
                else:
                    if not key:
                        n_skipped += 1
                    else:
                        n_failed += 1
                    bar.update(1)
                    continue

            if vec.shape != (dim,):
                raise RuntimeError(
                    f"CLIP output dim {vec.shape[0]} does not match configured "
                    f"embedding_dim {dim}. Pick a CLIP backbone whose native output "
                    f"matches configs/dev.yaml:representation.embedding_dim."
                )
            out[i] = vec
            n_done += 1
            bar.set_postfix(ok=n_done, poster=n_poster_fallback, skip=n_skipped, fail=n_failed)
            bar.update(1)

    log.info(
        "encode_trailers_complete",
        extra={
            "n_total": len(movie_keys),
            "n_encoded": n_done,
            "n_poster_fallback": n_poster_fallback,
            "n_skipped_no_key_or_poster": n_skipped,
            "n_failed": n_failed,
        },
    )
    return out


def encode_trailers_sharded(
    movie_keys: list[tuple[int, str | None, str | None]],
    shard_dir: Path,
    *,
    shard_size: int = 50,
    n_frames: int = 16,
    batch_size: int = 16,
    max_shards_per_run: int | None = None,
) -> tuple[np.ndarray, bool]:
    """Resumable, sharded version of encode_trailers with poster fallback.

    Splits ``movie_keys`` into contiguous shards of ``shard_size`` entries.
    Each shard is persisted as ``shard_dir / shard_{idx:05d}.npz`` containing
    arrays ``movie_ids`` (int64) and ``vectors`` (float32). Existing shards are
    loaded and validated; missing shards are embedded and saved atomically.
    When ``max_shards_per_run`` newly embedded shards have been produced the
    function returns early so that partial progress is visible in the caller.

    When a movie's trailer is unavailable or its fetch fails, the poster image
    is encoded as a fallback. A poster-fallback vector stored in a shard is
    locked in on subsequent runs (the shard is not re-encoded) — this matches
    the zero-row lock-in behavior that existed before the fallback was added.

    Designed to be called repeatedly across Colab sessions with the same
    ``shard_dir`` backed by Google Drive. Each call resumes from where the
    previous left off.

    Args:
        movie_keys:        List of ``(movie_id, youtube_key, poster_path)``
                           triples aligned to the split's row order. Either of
                           ``youtube_key`` or ``poster_path`` may be ``None``.
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
    total_zeros_retried = 0
    total_zeros_filled = 0
    all_complete = True

    for shard_idx in range(n_shards):
        start = shard_idx * shard_size
        end = min(start + shard_size, n_total)
        shard_keys = movie_keys[start:end]
        expected_ids = np.array([mid for mid, _, _ in shard_keys], dtype=np.int64)

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
            vectors = data["vectors"].copy()
            zero_indices = np.where(
                (np.abs(vectors).sum(axis=1) == 0) | np.isnan(vectors).any(axis=1)
            )[0]
            if zero_indices.size == 0:
                out[start:end] = vectors
                log.info(
                    "shard_skipped_existing",
                    extra={"shard_idx": shard_idx, "n_shards": n_shards, "shard_path": str(shard_path)},
                )
                continue
            n_filled = 0
            n_poster_retry = 0
            for j in zero_indices:
                movie_id, key, poster_path = shard_keys[j]
                vec: np.ndarray | None = None
                if key:
                    try:
                        vec = _encode_one(key, n_frames, batch_size)
                    except Exception as exc:
                        log.warning(
                            "trailer_encode_failed",
                            extra={"movie_id": movie_id, "youtube_key": key, "error": str(exc)},
                        )
                if vec is None:
                    vec = _encode_poster_one(poster_path)
                    if vec is not None:
                        n_poster_retry += 1
                if vec is not None:
                    vectors[j] = vec
                    n_filled += 1
            if n_filled > 0:
                tmp_path = shard_path.with_suffix(".tmp.npz")
                np.savez(tmp_path, movie_ids=expected_ids, vectors=vectors)
                os.replace(tmp_path, shard_path)
            total_zeros_retried += zero_indices.size
            total_zeros_filled += n_filled
            out[start:end] = vectors
            log.info(
                "shard_zeros_retried",
                extra={
                    "shard_idx": shard_idx,
                    "n_shards": n_shards,
                    "n_zeros": zero_indices.size,
                    "n_filled": n_filled,
                    "n_poster_fallback": n_poster_retry,
                    "shard_path": str(shard_path),
                },
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
        n_poster_fallback = 0
        n_failed = 0
        with tqdm(
            total=end - start,
            desc=f"shard {shard_idx}/{n_shards - 1}",
            unit="movie",
            leave=False,
        ) as bar:
            for j, (movie_id, key, poster_path) in enumerate(shard_keys):
                vec: np.ndarray | None = None

                if key:
                    try:
                        vec = _encode_one(key, n_frames, batch_size)
                    except Exception as exc:
                        log.warning(
                            "trailer_encode_failed",
                            extra={"movie_id": movie_id, "youtube_key": key, "error": str(exc)},
                        )

                if vec is None:
                    vec = _encode_poster_one(poster_path)
                    if vec is not None:
                        n_poster_fallback += 1
                    else:
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
                bar.set_postfix(ok=n_done, poster=n_poster_fallback, fail=n_failed)
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
                "n_poster_fallback": n_poster_fallback,
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
            "zeros_retried": total_zeros_retried,
            "zeros_filled": total_zeros_filled,
            "complete": all_complete,
        },
    )
    return out, all_complete
