"""Ground truth trajectory builder.

Produces a GroundTruthRow with an ordered list of (op, concept) operations
and a neutral intent description, grounded in a random sample from the live
catalogue. Both LLM passes use the judge model tier from eval/eval.yaml.

GT-builder knobs (max_movies, min_ops, max_ops) are read from the ``eval_harness:
gt_builder:`` section of ``eval/eval.yaml`` — an offline-only section ignored by
``get_settings()``.
"""
import hashlib
import logging
import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.data_access.eval.queries import create_ground_truth, get_ground_truth_by_slug
from backend.data_access.eval.types import GroundTruthRow
from backend.data_access.movies.queries import sample_movies_for_gt
from backend.llm import llm_harness
from backend.settings import get_config_hash
from eval.config import load_eval_harness_config
from eval.ground_truths.types import IntentDescriptionProposal, TrajectoryProposal

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_VALID_OPS = {"cluster", "merge", "focus", "cross_filter"}


async def build_ground_truth(slug: str, hint: str | None = None) -> GroundTruthRow:
    """Build and persist a ground truth trajectory for the given slug.

    Two LLM passes via the judge model from eval/eval.yaml:
    1. Trajectory proposal: sample N movies, propose min_ops–max_ops (op, concept) pairs.
    2. Intent description: write a neutral paragraph paraphrasing the trajectory.

    Builder knobs (max_movies, min_ops, max_ops) are read from the ``eval_harness:
    gt_builder:`` section of ``eval/eval.yaml``.  The prompt_hash is the SHA-256 of
    both rendered prompts concatenated.

    Args:
        slug: Unique identifier for this ground truth.
        hint: Optional free-text hint to guide the trajectory theme.

    Returns:
        Persisted ``GroundTruthRow``.

    Raises:
        ValueError:        If a ground truth with this slug already exists.
        FileNotFoundError: If eval/eval.yaml is missing.
        LLMParseError:     If either LLM pass returns invalid JSON.
    """
    if get_ground_truth_by_slug(slug) is not None:
        raise ValueError(f"ground truth slug already exists: {slug!r}")

    harness_cfg = load_eval_harness_config()
    gt_cfg = harness_cfg.gt_builder
    model = harness_cfg.judge

    fake_conversation_id = str(uuid.uuid4())
    accumulated_cost = 0.0

    movies = sample_movies_for_gt(gt_cfg.max_movies, seed=42)
    movie_dicts = [
        {"title": m.title, "release_year": m.release_year, "vote_average": m.vote_average}
        for m in movies
    ]
    seed_movie_ids = [m.id for m in movies]

    trajectory_prompt = _ENV.get_template("trajectory_v2.j2").render(
        movies=movie_dicts,
        min_ops=gt_cfg.min_ops,
        max_ops=gt_cfg.max_ops,
        hint=hint,
    )

    trajectory_resp = await llm_harness.call(
        run_id="gt_builder",
        conversation_id=fake_conversation_id,
        message_id="00000000-0000-0000-0000-000000000000",
        config_hash=get_config_hash(),
        model_and_version=model.name,
        provider=model.provider,
        seed=model.seed,
        max_tokens=model.max_tokens,
        step_type="gt_trajectory",
        messages=[{"role": "user", "content": trajectory_prompt}],
        cost_limit_usd=model.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=model.dry_run,
        response_schema=TrajectoryProposal,
    )
    accumulated_cost += trajectory_resp.cost_usd

    trajectory: TrajectoryProposal = trajectory_resp.parsed  # type: ignore[assignment]
    operations = [
        {"op": op["op"], "concept": op["concept"]}
        for op in trajectory.operations
        if op.get("op") in _VALID_OPS
    ]
    if not operations:
        from backend.llm.exceptions import LLMParseError
        raise LLMParseError(
            step_type="gt_trajectory",
            raw=f"no valid ops in trajectory response: {trajectory.operations!r}",
        )

    intent_prompt = _ENV.get_template("intent_description_v2.j2").render(
        operations=operations,
    )

    intent_resp = await llm_harness.call(
        run_id="gt_builder",
        conversation_id=fake_conversation_id,
        message_id="00000000-0000-0000-0000-000000000000",
        config_hash=get_config_hash(),
        model_and_version=model.name,
        provider=model.provider,
        seed=model.seed,
        max_tokens=model.max_tokens,
        step_type="gt_intent_description",
        messages=[{"role": "user", "content": intent_prompt}],
        cost_limit_usd=model.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=model.dry_run,
        response_schema=IntentDescriptionProposal,
    )

    intent_desc: IntentDescriptionProposal = intent_resp.parsed  # type: ignore[assignment]
    prompt_hash = hashlib.sha256(
        (trajectory_prompt + intent_prompt).encode()
    ).hexdigest()

    log.info(
        "gt_built",
        extra={
            "slug": slug,
            "n_operations": len(operations),
            "prompt_hash": prompt_hash[:8],
        },
    )

    gt_id = create_ground_truth(
        slug=slug,
        intent_description=intent_desc.text,
        operations=operations,
        prompt_hash=prompt_hash,
        seed_movie_ids=seed_movie_ids,
    )

    row = get_ground_truth_by_slug(slug)
    if row is None:
        raise RuntimeError(f"ground truth {gt_id} not found immediately after creation")
    return row
