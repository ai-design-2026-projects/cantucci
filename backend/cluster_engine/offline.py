import logging
import uuid

import numpy as np

from backend.cluster_engine.fusion import fuse_batch
from backend.cluster_engine.labeling import label_cluster
from backend.cluster_engine.soft_cluster import hdbscan_soft
from backend.data_access.connection import transaction
from backend.data_access.cluster_snapshots.queries import (
    create_cluster,
    create_cluster_snapshot,
    create_memberships,
)
from backend.settings import get_settings

log = logging.getLogger(__name__)

_TOP_EXEMPLARS = 15


def _load_all_embeddings() -> tuple[list[int], np.ndarray, np.ndarray | None]:
    """Fetch text_embedding and review_embedding for all movies that have text_embedding.

    Returns:
        Tuple of (movie_ids, text_embeddings, review_embeddings).
        review_embeddings is None if no movie has a review_embedding.
        Rows with NULL review_embedding are represented as all-zero vectors.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, text_embedding, review_embedding
            FROM movies
            WHERE text_embedding IS NOT NULL
            ORDER BY id
            """
        ).fetchall()

    if not rows:
        raise RuntimeError("No movies with text_embedding found. Run ingestion first.")

    movie_ids = [r[0] for r in rows]
    text_embs = np.array([list(r[1]) for r in rows], dtype=np.float32)

    has_any_review = any(r[2] is not None for r in rows)
    if has_any_review:
        review_embs = np.zeros_like(text_embs)
        for i, r in enumerate(rows):
            if r[2] is not None:
                review_embs[i] = list(r[2])
    else:
        review_embs = None

    log.info("embeddings_loaded", extra={"n_movies": len(movie_ids), "has_reviews": has_any_review})
    return movie_ids, text_embs, review_embs


def _write_fused_embeddings(movie_ids: list[int], fused: np.ndarray) -> None:
    """Persist fused_embedding back to the movies table.

    Args:
        movie_ids: List of TMDB IDs in the same order as fused rows.
        fused:     Float32 array of shape (n, 1024).
    """
    rows = [(fused[i].tolist(), mid) for i, mid in enumerate(movie_ids)]
    with transaction() as conn:
        conn.executemany(
            "UPDATE movies SET fused_embedding = %s::vector WHERE id = %s",
            rows,
        )
    log.info("fused_embeddings_written", extra={"n_movies": len(movie_ids)})


def _write_umap_coords(movie_ids: list[int], fused: np.ndarray, seed: int) -> None:
    """Compute UMAP 2D and persist umap_x / umap_y to the movies table.

    Args:
        movie_ids: TMDB IDs in row order.
        fused:     Float32 array of shape (n, 1024).
        seed:      Random seed from config.
    """
    from umap import UMAP

    cfg_umap = get_settings().umap
    reducer = UMAP(
        n_components=2,
        n_neighbors=cfg_umap.n_neighbors,
        min_dist=cfg_umap.min_dist,
        metric="cosine",
        random_state=seed,
    )
    coords = reducer.fit_transform(fused)
    rows = [(float(coords[i, 0]), float(coords[i, 1]), mid) for i, mid in enumerate(movie_ids)]
    with transaction() as conn:
        conn.executemany(
            "UPDATE movies SET umap_x = %s, umap_y = %s WHERE id = %s",
            rows,
        )
    log.info("umap_coords_written", extra={"n_movies": len(movie_ids)})


async def build_root_cluster_snapshot(seed: int) -> uuid.UUID:
    """Compute the base HDBSCAN clustering over all movies and persist it as the root cluster snapshot.

    Steps:
      1. Load text + review embeddings from DB.
      2. Compute fused embeddings; write back to movies.fused_embedding.
      3. Compute UMAP 2D; write back to movies.umap_x/y.
      4. Run HDBSCAN soft clustering on fused embeddings.
      5. Persist root cluster snapshot, clusters (with LLM labels), and memberships.

    Args:
        seed: RNG seed from config (used for UMAP determinism).

    Returns:
        UUID of the created root cluster snapshot.
    """
    cfg = get_settings()
    base_cfg = cfg.clustering.base
    fusion_cfg = cfg.fusion

    movie_ids, text_embs, review_embs = _load_all_embeddings()

    fused = fuse_batch(text_embs, review_embs, fusion_cfg.text_weight, fusion_cfg.review_weight)
    _write_fused_embeddings(movie_ids, fused)
    _write_umap_coords(movie_ids, fused, seed)

    result = hdbscan_soft(
        fused,
        min_cluster_size=base_cfg.min_cluster_size,
        min_samples=base_cfg.min_samples,
        cluster_selection_method=base_cfg.cluster_selection_method,
        cluster_selection_epsilon=base_cfg.cluster_selection_epsilon,
    )

    cluster_snapshot_id = create_cluster_snapshot(
        operation="base",
        params={
            "algorithm": base_cfg.algorithm,
            "min_cluster_size": base_cfg.min_cluster_size,
            "min_samples": base_cfg.min_samples,
            "cluster_selection_method": base_cfg.cluster_selection_method,
            "cluster_selection_epsilon": base_cfg.cluster_selection_epsilon,
            "seed": seed,
            "n_movies": len(movie_ids),
            "n_clusters": result.n_clusters,
        },
    )

    accumulated_cost = 0.0
    for cluster_idx in range(result.n_clusters):
        col = result.probabilities[:, cluster_idx]
        top_indices = np.argsort(col)[::-1][:_TOP_EXEMPLARS]
        exemplar_ids = [movie_ids[i] for i in top_indices if col[i] > 0]

        label, summary = await label_cluster(
            exemplar_movie_ids=exemplar_ids,
            conversation_id="offline",
            accumulated_cost=accumulated_cost,
        )

        cluster_id = create_cluster(
            cluster_snapshot_id=cluster_snapshot_id,
            label=label,
            summary=summary,
            exemplar_movie_ids=exemplar_ids,
        )

        memberships: list[tuple[uuid.UUID, int, float]] = [
            (cluster_id, movie_ids[i], float(col[i]))
            for i in range(len(movie_ids))
            if col[i] >= base_cfg.prob_threshold
        ]
        create_memberships(memberships)

        log.info(
            "cluster_persisted",
            extra={
                "cluster_idx": cluster_idx,
                "label": label,
                "n_members": len(memberships),
                "cluster_snapshot_id": str(cluster_snapshot_id),
            },
        )

    log.info(
        "root_cluster_snapshot_complete",
        extra={"cluster_snapshot_id": str(cluster_snapshot_id), "n_clusters": result.n_clusters},
    )
    return cluster_snapshot_id
