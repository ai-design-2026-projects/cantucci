import logging
from pathlib import Path
from uuid import UUID, uuid4

from backend.api.types import ClusterAssignment, ClusterSnapshot
from backend.cluster.types import ClusterRefineResponse
from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.llm.types import LLMParseError
from backend.retrieval.tools import metadata_fetcher
from backend.settings import get_config_hash, get_settings

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent.parent / "prompts" / "refiner")

_STEP_TYPE = "cluster_refine"

# Cap on the overview snippet rendered into the prompt per film, in characters.
# Refinement payloads can grow linearly in the pool size; capping the overview
# keeps the prompt within the harness's max_tokens envelope on larger pools.
_OVERVIEW_SNIPPET_LIMIT = 240


def refine(
    *,
    prior_clusters: list[ClusterSnapshot],
    user_query: str,
    asked_question: str,
    user_answer: str,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> list[ClusterSnapshot]:
    """
    Refine *prior_clusters* given the clarifying Q&A in a single LLM call.
    Args:
        prior_clusters:       The previous turn's ``ClusterSnapshot`` list.
                              The union of their assignments forms the pool of
                              films the refiner may keep, move, or drop.
        user_query:           The oracle's original session-level query.
        asked_question:       The clarifying question the system asked on the
                              previous turn. Required (the refinement path
                              only fires when both Q and A are present).
        user_answer:          The oracle's reply to *asked_question*.
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        accumulated_cost_usd: Running USD cost for the current turn.
        dry_run:              If ``True``, skip the live LLM and use the fixture.

    Returns:
        Refined ``list[ClusterSnapshot]``. New UUIDs are minted for every
        cluster because refinement can split/merge prior clusters; reusing
        prior IDs would misrepresent identity.

    Raises:
        LLMParseError:     If the harness exhausts its retry budget on schema
                           validation, or if the validated response references
                           a ``movie_id`` outside the prior pool.
        CostLimitExceeded: If the session budget is exhausted.
    """
    cfg = get_settings()
    config_hash = get_config_hash()
    model_and_version = cfg.model.name

    # Collect the pool of movie_ids the LLM may operate on — every film in the
    # prior clusters, including ones the previous turn excluded (the LLM may
    # bring them back if the answer warrants).
    pool_ids: list[int] = []
    seen: set[int] = set()
    for c in prior_clusters:
        for a in c.assignments:
            if a.movie_id not in seen:
                pool_ids.append(a.movie_id)
                seen.add(a.movie_id)
    allowed_set = set(pool_ids)

    metas = metadata_fetcher.fetch(pool_ids)
    meta_by_id = {m.movie_id: m for m in metas}

    # Load the prior clusters into the prompt format
    prior_payload = [
        {
            "cluster_id": str(c.id),
            "name": c.name,
            "description": c.description or "",
            "films": [
                {
                    "movie_id": a.movie_id,
                    "title": (
                        meta_by_id[a.movie_id].title
                        if a.movie_id in meta_by_id
                        else (a.title or str(a.movie_id))
                    ),
                    "overview": _overview_snippet(meta_by_id, a.movie_id),
                    "excluded": a.excluded,
                }
                for a in c.assignments
            ],
        }
        for c in prior_clusters
    ]

    # List of all films the LLM can mention in its response
    allowed_films = [
        {
            "movie_id": mid,
            "title": meta_by_id[mid].title if mid in meta_by_id else str(mid),
        }
        for mid in pool_ids
    ]

    system_text, prompt_hash = load_prompt(
        "cluster_refine_v2",
        {
            "user_query": user_query,
            "asked_question": asked_question,
            "user_answer": user_answer,
            "prior_clusters": prior_payload,
            "allowed_films": allowed_films,
        },
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_answer},
    ]

    response = llm_harness.call(
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        config_hash=config_hash,
        model_and_version=model_and_version,
        provider=cfg.model.provider,
        seed=cfg.model.seed,
        max_tokens=cfg.model.max_tokens,
        step_type=_STEP_TYPE,
        messages=messages,
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost_usd,
        dry_run=dry_run,
        response_schema=ClusterRefineResponse,
    )

    # response.parsed is guaranteed non-None when response_schema is set.
    assert isinstance(response.parsed, ClusterRefineResponse)
    parsed: ClusterRefineResponse = response.parsed

    # The schema cannot enforce pool membership because it has no view of the
    # allowed set.x.
    offending: list[int] = []
    for c in parsed.clusters:
        for a in c.assignments:
            if a.movie_id not in allowed_set:
                offending.append(a.movie_id)
    if offending:
        log.warning(
            "cluster refiner: out-of-pool movie_ids in refine response",
            extra={
                "session_id": str(session_id),
                "offending": offending,
                "pool_size": len(allowed_set),
            },
        )
        raise LLMParseError(step_type=_STEP_TYPE, raw=response.content)

    snapshots: list[ClusterSnapshot] = []
    kept_ids: set[int] = set()
    for c in parsed.clusters:
        assignments = [
            ClusterAssignment(
                movie_id=a.movie_id,
                score=float(a.score),
                excluded=False,
                title=meta_by_id[a.movie_id].title if a.movie_id in meta_by_id else None,
            )
            for a in c.assignments
        ]
        for a in assignments:
            kept_ids.add(a.movie_id)
        snapshots.append(
            ClusterSnapshot(
                id=uuid4(),
                name=c.name,
                description=c.description,
                level=0,
                parent_cluster_id=None,
                assignments=assignments,
            )
        )

    log.debug(
        "cluster refiner reasoning",
        extra={"session_id": str(session_id), "reasoning": parsed.reasoning},
    )
    log.info(
        "cluster refiner complete",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "n_clusters_in": len(prior_clusters),
            "n_clusters_out": len(snapshots),
            "n_films_in_pool": len(pool_ids),
            "n_films_kept": len(kept_ids),
        },
    )
    return snapshots


def _overview_snippet(meta_by_id: dict, movie_id: int) -> str:
    """Return a truncated overview for *movie_id* suitable for prompt rendering."""
    meta = meta_by_id.get(movie_id)
    if meta is None or not meta.overview:
        return ""
    overview = meta.overview.strip()
    if len(overview) <= _OVERVIEW_SNIPPET_LIMIT:
        return overview
    return overview[: _OVERVIEW_SNIPPET_LIMIT - 1].rstrip() + "…"
