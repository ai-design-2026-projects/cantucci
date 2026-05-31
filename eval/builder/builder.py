"""Ground-truth bundle builder: single LLM pass per bundle."""
import hashlib
import logging
import random

from jinja2 import Environment, FileSystemLoader

from backend.llm import llm_harness
from backend.llm.exceptions import LLMParseError
from backend.settings import get_config_hash
from eval.builder.types import GroundTruthProposal
from eval.config import eval_prompts_dir, load_eval_harness_config
from eval.personas.store import write_bundle
from eval.personas.types import PersonaBundle
from eval.types import CONCEPT_KINDS, CONCEPT_SPACES, NAVIGATION_OPERATIONS, VERBOSITIES, OpSpec

log = logging.getLogger(__name__)

_ENV = Environment(loader=FileSystemLoader(str(eval_prompts_dir("builder"))), autoescape=False)

_LENSES = [
    "visual style and cinematography",
    "political or ideological subtext",
    "cultural geography — a specific country, city, or region",
    "a historical period or decade",
    "gender and power dynamics",
    "social class and economic tension",
    "narrative structure — non-linear, fragmented, or unreliable",
    "sound design, silence, or music as storytelling",
    "the relationship between humans and their physical environment",
    "religion, ritual, or spirituality",
    "childhood, adolescence, or coming-of-age",
    "violence and its consequences — psychological or physical",
    "comedy mode — absurdist, satirical, or deadpan",
    "a specific director's filmography or national cinema movement",
    "technology, modernity, and alienation",
    "family structure and generational conflict",
    "crime, morality, and complicity",
    "the body — illness, desire, physical transformation",
    "documentary realism vs stylised artifice",
    "colonialism, diaspora, or cultural displacement",
]


def _validate_proposal(proposal: GroundTruthProposal) -> None:
    """Raise LLMParseError if any operation in the proposal is invalid.

    Args:
        proposal: The LLM-produced ground truth proposal to validate.

    Raises:
        LLMParseError: On empty operations list or invalid op/kind/space values.
    """
    if not proposal.operations:
        raise LLMParseError(step_type="gt_builder", raw="proposal has no operations")
    for i, op in enumerate(proposal.operations):
        if op.op not in NAVIGATION_OPERATIONS:
            raise LLMParseError(
                step_type="gt_builder",
                raw=f"operation[{i}].op {op.op!r} is not in NAVIGATION_OPERATIONS",
            )
        if op.kind is not None and op.kind not in CONCEPT_KINDS:
            raise LLMParseError(
                step_type="gt_builder",
                raw=f"operation[{i}].kind {op.kind!r} is not in CONCEPT_KINDS",
            )
        if op.space is not None and op.space not in CONCEPT_SPACES:
            raise LLMParseError(
                step_type="gt_builder",
                raw=f"operation[{i}].space {op.space!r} is not in CONCEPT_SPACES",
            )


async def build_bundle(
    slug: str | None = None,
    *,
    verbosity: str = "medium",
    patience: float = 0.7,
    hint: str | None = None,
    lens: str | None = None,
    target_ops: int | None = None,
    seed_offset: int = 0,
) -> PersonaBundle:
    """Build and persist a single bundle via one LLM call.

    Renders the ground-truth prompt, calls the judge-tier model once, validates
    the response, and writes the bundle to ``eval/personas/conf/<slug>.yaml``.
    When ``slug`` is omitted it is derived from the generated intent description.

    Args:
        slug:        Unique identifier for this bundle. Derived from intent if omitted.
        verbosity:   Oracle reply-length dial: one of ``VERBOSITIES``.
        patience:    Oracle patience in [0.0, 1.0].
        hint:        Optional explicit theme hint. When omitted the model invents freely.
        lens:        Optional cinematic angle to orient the invented theme (e.g.
                     ``"political subtext"``). Ignored when ``hint`` is provided.
        target_ops:  Exact number of operations to request. Defaults to a random value
                     drawn from the ``[gt_builder.min_ops, gt_builder.max_ops]`` range.
        seed_offset: Added to the model seed to vary outputs across batch calls.

    Returns:
        The written ``PersonaBundle``.

    Raises:
        LLMParseError: If the LLM returns an invalid or empty operations list.
    """
    harness_cfg = load_eval_harness_config()
    model = harness_cfg.judge

    if target_ops is None:
        target_ops = random.randint(harness_cfg.gt_builder.min_ops, harness_cfg.gt_builder.max_ops)

    template = _ENV.get_template("ground_truth_v1.j2")
    prompt = template.render(hint=hint, lens=lens, target_ops=target_ops)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

    resp = await llm_harness.call(
        run_id="eval",
        conversation_id="00000000-0000-0000-0000-000000000000",
        message_id="00000000-0000-0000-0000-000000000000",
        config_hash=get_config_hash(),
        model_and_version=model.name,
        provider=model.provider,
        seed=model.seed + seed_offset,
        max_tokens=model.max_tokens,
        step_type="gt_builder",
        messages=[{"role": "user", "content": prompt}],
        cost_limit_usd=model.cost_limit_usd,
        accumulated_cost_usd=0.0,
        dry_run=model.dry_run,
        response_schema=GroundTruthProposal,
    )

    proposal: GroundTruthProposal = resp.parsed  # type: ignore[assignment]
    _validate_proposal(proposal)

    resolved_slug = slug if slug is not None else proposal.slug
    ops = [
        OpSpec(op=o.op, concept=o.concept, kind=o.kind, space=o.space)
        for o in proposal.operations
    ]
    bundle = PersonaBundle(
        slug=resolved_slug,
        verbosity=verbosity,
        patience=patience,
        intent_description=proposal.intent_description,
        operations=ops,
        prompt_hash=prompt_hash,
    )
    write_bundle(bundle)

    log.info(
        "bundle_built",
        extra={"slug": resolved_slug, "num_ops": len(ops), "cost_usd": resp.cost_usd},
    )
    return bundle


async def build_random_batch(n: int) -> list[PersonaBundle]:
    """Build ``n`` bundles with freely invented themes and randomised persona dials.

    Each bundle's slug is derived from its generated intent description. Verbosity
    cycles across all values; patience and op count are randomised per bundle. The
    LLM seed is varied per unit to ensure output diversity.

    Args:
        n: Number of bundles to build. Must be >= 1.

    Returns:
        List of ``PersonaBundle`` instances in creation order.

    Raises:
        ValueError:    If ``n < 1``.
        LLMParseError: If any individual LLM call returns an invalid response.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")

    harness_cfg = load_eval_harness_config()
    bundles: list[PersonaBundle] = []

    for i in range(1, n + 1):
        verbosity = VERBOSITIES[i % len(VERBOSITIES)]
        patience = round(random.uniform(0.3, 1.0), 2)
        target_ops = random.randint(harness_cfg.gt_builder.min_ops, harness_cfg.gt_builder.max_ops)
        lens = _LENSES[(i - 1) % len(_LENSES)]

        log.info("bundle_batch_start", extra={"index": i, "total": n, "target_ops": target_ops, "verbosity": verbosity, "lens": lens})
        bundle = await build_bundle(
            verbosity=verbosity,
            patience=patience,
            lens=lens,
            target_ops=target_ops,
            seed_offset=i,
        )
        log.info("bundle_batch_done", extra={"index": i, "total": n, "slug": bundle.slug, "num_ops": len(bundle.operations)})
        bundles.append(bundle)

    return bundles
