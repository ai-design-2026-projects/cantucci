"""cluster_updater — re-cluster a fixed candidate pool from a prior turn.

Skips reformulation and vector search; fetches embeddings for the supplied
movie IDs and re-runs HDBSCAN to produce fresh soft assignments.

When the oracle's prior choice is provided, an LLM call re-scores each movie's
relevance to that choice and the preference scores are multiplied into the
HDBSCAN membership matrix so that accepted films rank higher in cluster assignments.
"""

import json
import logging
from pathlib import Path
from uuid import UUID

import numpy as np

from backend.cluster.tools import embedding_fetcher, soft_cluster_engine
from backend.cluster.tools.soft_cluster_engine import SoftClusterResult
from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.llm.types import LLMParseError
from backend.settings import get_settings

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent.parent / "prompts")

_STEP_TYPE = "cluster_rescore"


def update(
    movie_ids: list[int],
    *,
    metas: list,
    min_cluster_size: int,
    min_samples: int,
    cluster_selection_method: str = "eom",
    accepted_cluster: dict | None = None,
    user_query: str = "",
    session_id: UUID | None = None,
    run_id: UUID | None = None,
    turn_id: UUID | None = None,
    config_hash: str = "",
    model_version: str = "",
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> tuple[list[int], SoftClusterResult]:
    """Re-cluster *movie_ids* and optionally re-score by the oracle's prior choice.

    Step 1: fetch embeddings and run HDBSCAN to produce a base membership matrix.
    Step 2 (when *accepted_cluster* is set and not *dry_run*): call an LLM to score
    each movie's relevance to the oracle's accepted or rejected cluster, then multiply
    those preference scores into the membership matrix row-wise so that favoured films
    rank higher in soft assignments.

    Args:
        movie_ids:                TMDB movie IDs from a prior turn's pool.
        metas:                    Movie metadata objects (with ``movie_id``, ``title``,
                                  ``overview``) aligned with *movie_ids*; used to build
                                  the LLM context without an extra DB round-trip.
        min_cluster_size:         HDBSCAN ``min_cluster_size`` (from config).
        min_samples:              HDBSCAN ``min_samples`` (from config).
        cluster_selection_method: ``"eom"`` (default) or ``"leaf"``.
        accepted_cluster:         Dict with keys ``name``, ``description``,
                                  ``feedback_type`` (``"accept"`` or ``"reject"``).
                                  When ``None``, the LLM step is skipped.
        user_query:               Oracle's current query; included in the rescore prompt.
        session_id:               UUID of the current session (for LLM harness logging).
        run_id:                   UUID of the parent run.
        turn_id:                  UUID of the current turn.
        config_hash:              SHA-256 prefix of the session's YAML config snapshot.
        model_version:            LLM model string.
        accumulated_cost_usd:     Running USD cost for the current turn.
        dry_run:                  If ``True``, skip the LLM rescore call.

    Returns:
        Tuple ``(kept_ids, result)`` where *kept_ids* is the subset of *movie_ids*
        found in the catalogue and *result* is the ``SoftClusterResult`` with a
        membership matrix that reflects the oracle's preference when applicable.

    Raises:
        ValueError:    If no embeddings are found for the supplied IDs, or fewer
                       than 2 valid embeddings are returned.
        LLMParseError: If the LLM returns non-JSON, a non-list, a list of the wrong
                       length, or entries missing ``movie_id`` / ``score`` keys.
    """
    kept_ids, embeddings = embedding_fetcher.fetch(movie_ids)

    log.debug(
        "cluster_updater: re-clustering prior candidates",
        extra={"n_requested": len(movie_ids), "n_kept": len(kept_ids)},
    )

    result = soft_cluster_engine.cluster(
        embeddings,
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_method=cluster_selection_method,
    )

    if result.n_clusters == 0 or result.membership is None:
        return kept_ids, result

    if accepted_cluster is None or dry_run:
        return kept_ids, result

    meta_by_id = {m.movie_id: m for m in metas}
    movies_payload = [
        {
            "movie_id": mid,
            "title": meta_by_id[mid].title if mid in meta_by_id else str(mid),
            "overview": (meta_by_id[mid].overview or "") if mid in meta_by_id else "",
        }
        for mid in kept_ids
    ]

    cfg = get_settings()
    system_text, prompt_hash = load_prompt(
        "cluster_rescore_v1",
        {
            "user_query": user_query,
            "cluster_name": accepted_cluster["name"],
            "cluster_description": accepted_cluster["description"],
            "feedback_type": accepted_cluster["feedback_type"],
            "movies": movies_payload,
        },
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": json.dumps(movies_payload)},
    ]

    response = llm_harness.call(
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        config_hash=config_hash,
        model_and_version=model_version,
        provider=cfg.model.provider,
        seed=cfg.model.seed,
        max_tokens=cfg.model.max_tokens,
        step_type=_STEP_TYPE,
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost_usd,
    )

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)

    if not isinstance(parsed, list) or len(parsed) != len(kept_ids):
        raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)

    preference_scores = np.ones(len(kept_ids), dtype=np.float32)
    id_to_idx = {mid: i for i, mid in enumerate(kept_ids)}
    for entry in parsed:
        if not isinstance(entry.get("movie_id"), int) or not isinstance(
            entry.get("score"), (int, float)
        ):
            raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)
        idx = id_to_idx.get(entry["movie_id"])
        if idx is not None:
            preference_scores[idx] = float(entry["score"])

    result.membership = result.membership * preference_scores[:, np.newaxis]

    log.debug(
        "cluster_updater: applied preference rescore",
        extra={
            "session_id": str(session_id),
            "feedback_type": accepted_cluster["feedback_type"],
            "cluster_name": accepted_cluster["name"],
        },
    )

    return kept_ids, result
