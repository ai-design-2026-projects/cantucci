"""Offline ground-truth builder.

Samples N seed films from the eval holdout parquet, expands each seed to its
nearest neighbours in embedding space using cosine similarity, aggregates the
results into a ranked list, calls an LLM to write a neutral taste description,
and writes a ``configs/ground_truths/<slug>.yaml`` file.

Usage::

    python -m eval.oracle.gt_builder \\
        --n-seed 5 \\
        --n-gt 40 \\
        --seed 42 \\
        --slug arthouse-eurodrama \\
        --out configs/ground_truths/arthouse-eurodrama.yaml

The same flags always produce the same YAML (given the same HF artifact), so
the file is deterministic and its SHA-256 hash is stable for replay.

Parquet schema (produced by ``notebooks/embed_in_colab.ipynb``):
  ``tmdb_id``   — int TMDB movie identifier.
  ``title``     — str English title.
  ``release_year`` — int or NaN.
  ``genres``    — JSON-encoded list of genre strings.
  ``embedding`` — float32 list (``representation.embedding_dim`` dimensions).
"""

import argparse
import asyncio
import hashlib
import json
import logging
import random
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from backend.logging_setup import configure_logging
from backend.llm.prompts import make_prompt_loader
from backend.settings import CONFIGS_DIR, PROJECT_ROOT, get_settings
from db.ingestion.fetch import fetch_artifact
from eval.shared.llm_gateway import LLMGateway

log = logging.getLogger(__name__)

_PROMPTS_DIR = PROJECT_ROOT / "eval" / "oracle" / "prompts"


def _cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between *query* and every row in *matrix*.

    Args:
        query:  1-D float32 array of shape ``(dim,)``.
        matrix: 2-D float32 array of shape ``(n, dim)``.

    Returns:
        1-D float32 array of shape ``(n,)`` with values in ``[-1, 1]``.
    """
    q = query / (np.linalg.norm(query) + 1e-9)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    normed = matrix / norms
    return normed @ q


def build_ground_truth(
    *,
    slug: str,
    n_seed: int,
    n_gt: int,
    seed: int,
    llm: LLMGateway,
    out_path: Path,
) -> None:
    """Build a ground-truth YAML from the eval holdout parquet and write it.

    Args:
        slug:     Kebab-case identifier for this ground truth (e.g. ``"arthouse-eurodrama"``).
        n_seed:   Number of films to sample as seeds from eval_holdout.
        n_gt:     Total number of films in the final ground-truth set (including seeds).
        seed:     RNG seed for deterministic sampling.
        llm:      LLM gateway used to generate the taste description.
        out_path: Destination YAML file path.

    Raises:
        FileNotFoundError: If the eval_holdout artifact cannot be fetched.
        ValueError:        If ``n_gt > len(eval_holdout)`` or ``n_seed > n_gt``.
    """
    cfg = get_settings()
    artifact_path = fetch_artifact(
        cfg.ingestion.hf_repo, cfg.ingestion.artifacts.eval_holdout
    )
    log.info("gt_builder: loaded eval_holdout from %s", artifact_path)

    import pandas as pd

    df = pd.read_parquet(artifact_path)
    embeddings = np.array(df.pop("embedding").tolist(), dtype=np.float32)
    for col in ("genres",):
        if col in df.columns:
            df[col] = df[col].apply(lambda v: json.loads(v) if isinstance(v, str) else v or [])

    if len(df) < n_seed:
        raise ValueError(f"eval_holdout has only {len(df)} films; cannot sample {n_seed} seeds")
    if n_seed > n_gt:
        raise ValueError(f"n_seed ({n_seed}) must be <= n_gt ({n_gt})")

    rng = random.Random(seed)
    seed_indices = sorted(rng.sample(range(len(df)), n_seed))
    seed_rows = df.iloc[seed_indices]
    seed_embeddings = embeddings[seed_indices]

    similarity_scores = np.zeros(len(df), dtype=np.float32)
    for emb in seed_embeddings:
        similarity_scores += _cosine_similarity(emb, embeddings)
    similarity_scores[seed_indices] = -1.0  # exclude seeds from ranking

    top_indices = np.argsort(-similarity_scores)[: n_gt - n_seed]
    gt_indices = sorted(seed_indices) + sorted(top_indices.tolist())

    seed_movie_ids: list[int] = seed_rows["tmdb_id"].tolist()
    gt_movie_ids: list[int] = df.iloc[gt_indices]["tmdb_id"].tolist()

    def _film_stub(row: Any) -> dict[str, Any]:
        return {
            "title": row.title,
            "release_year": int(row.release_year) if not pd.isna(row.release_year) else None,
            "genres": row.genres if isinstance(row.genres, list) else [],
        }

    seed_films = [_film_stub(row) for row in seed_rows.itertuples()]
    gt_films = [_film_stub(df.iloc[i]) for i in gt_indices]  # type: ignore[arg-type]

    load_prompt = make_prompt_loader(_PROMPTS_DIR)
    description_text, _ = load_prompt(
        "ground_truth_description_v1",
        {"seed_films": seed_films, "gt_films": gt_films},
    )

    description = asyncio.run(
        llm.call(
            messages=[
                {"role": "system", "content": "You are a concise film critic."},
                {"role": "user", "content": description_text},
            ],
            step_type="gt_builder",
            prompt_hash=hashlib.sha256(description_text.encode()).hexdigest()[:8],
        )
    )

    data: dict[str, Any] = {
        "id": slug,
        "seed_movie_ids": seed_movie_ids,
        "gt_movie_ids": gt_movie_ids,
        "description": description.strip(),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = yaml.dump(data, allow_unicode=True, sort_keys=False).encode()
    data["gt_hash"] = hashlib.sha256(raw_bytes).hexdigest()[:8]

    out_path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))
    log.info("gt_builder: wrote %s (gt_hash=%s)", out_path, data["gt_hash"])


def main() -> None:
    """CLI entry point for the ground-truth builder."""
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Build a ground-truth YAML from the eval holdout parquet."
    )
    parser.add_argument("--n-seed", type=int, default=5, help="Seed films to sample")
    parser.add_argument("--n-gt", type=int, default=40, help="Total GT set size")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for sampling")
    parser.add_argument("--slug", required=True, help="Kebab-case ground-truth ID")
    parser.add_argument(
        "--out",
        type=Path,
        help="Output YAML path (default: configs/ground_truths/<slug>.yaml)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Use LLM fixture, skip API call")
    args = parser.parse_args()

    out_path: Path = args.out or (CONFIGS_DIR / "ground_truths" / f"{args.slug}.yaml")
    cfg = get_settings()
    if cfg.eval is None:
        raise RuntimeError("No eval: block in active config. Add it to configs/default.yaml.")

    llm = LLMGateway(
        model_name=cfg.eval.oracle.model.name,
        provider=cfg.eval.oracle.model.provider,
        seed=cfg.eval.oracle.model.seed,
        max_tokens=cfg.eval.oracle.model.max_tokens,
        cost_limit_usd=cfg.eval.oracle.cost_limit_usd,
        dry_run=args.dry_run,
        config_hash="gt_builder",
    )

    build_ground_truth(
        slug=args.slug,
        n_seed=args.n_seed,
        n_gt=args.n_gt,
        seed=args.seed,
        llm=llm,
        out_path=out_path,
    )
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
