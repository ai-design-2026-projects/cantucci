"""Ground-truth bundle builder: single LLM pass per bundle."""
import hashlib
import logging
import random
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.llm import llm_harness
from backend.llm.exceptions import LLMParseError
from backend.settings import get_config_hash
from eval.build.types import GroundTruthProposal
from eval.config import load_eval_harness_config
from eval.personas.store import write_bundle
from eval.personas.types import PersonaBundle
from eval.types import CONCEPT_KINDS, CONCEPT_SPACES, NAVIGATION_OPERATIONS, OpSpec

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_VERBOSITIES = ("terse", "medium", "verbose")

_HINTS = [
    "films about identity and transformation",
    "slow cinema and contemplative narratives",
    "heist and crime procedurals",
    "coming-of-age stories across different cultures",
    "science fiction with strong philosophical themes",
    "horror subgenres: body horror vs psychological vs supernatural",
    "female-directed films across different decades",
    "films set in a single location",
    "war films from different national perspectives",
    "road movies and journeys of self-discovery",
    "dark comedies and satire",
    "films with unreliable narrators",
    "neo-noir aesthetics",
    "family dramas across different social classes",
    "surrealist and experimental cinema",
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
    slug: str,
    *,
    verbosity: str = "medium",
    patience: float = 0.7,
    hint: str | None = None,
) -> PersonaBundle:
    """Build and persist a single bundle via one LLM call.

    Renders the ground-truth prompt, calls the judge-tier model once, validates
    the response, and writes the bundle to ``eval/personas/conf/<slug>.yaml``.

    Args:
        slug:      Unique identifier for this bundle. Raises if the file already exists.
        verbosity: Oracle reply-length dial: ``"terse"``, ``"medium"``, or ``"verbose"``.
        patience:  Oracle patience in [0.0, 1.0].
        hint:      Optional theme hint injected into the prompt.

    Returns:
        The written ``PersonaBundle``.

    Raises:
        FileExistsError: If ``eval/personas/conf/<slug>.yaml`` already exists.
        LLMParseError:   If the LLM returns an invalid or empty operations list.
    """
    harness_cfg = load_eval_harness_config()
    model = harness_cfg.judge

    template = _ENV.get_template("ground_truth_v1.j2")
    prompt = template.render(
        hint=hint,
        min_ops=harness_cfg.gt_builder.min_ops,
        max_ops=harness_cfg.gt_builder.max_ops,
    )
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

    resp = await llm_harness.call(
        run_id="eval",
        conversation_id="00000000-0000-0000-0000-000000000000",
        message_id="00000000-0000-0000-0000-000000000000",
        config_hash=get_config_hash(),
        model_and_version=model.name,
        provider=model.provider,
        seed=model.seed,
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

    ops = [
        OpSpec(op=o.op, concept=o.concept, kind=o.kind, space=o.space)
        for o in proposal.operations
    ]
    bundle = PersonaBundle(
        slug=slug,
        verbosity=verbosity,
        patience=patience,
        intent_description=proposal.intent_description,
        operations=ops,
        prompt_hash=prompt_hash,
    )
    write_bundle(bundle)

    log.info(
        "bundle_built",
        extra={"slug": slug, "num_ops": len(ops), "cost_usd": resp.cost_usd},
    )
    return bundle


async def build_random_batch(n: int) -> list[PersonaBundle]:
    """Build ``n`` bundles with randomised themes and persona dials.

    Each bundle gets a unique auto-slug (``rand-001``, ``rand-002``, …), a
    randomly chosen verbosity and patience, and a rotating theme hint drawn
    from the built-in hint list.  The LLM seed is varied per unit to encourage
    diversity despite using the same prompt template.

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
        slug = f"rand-{i:03d}"
        verbosity = _VERBOSITIES[i % len(_VERBOSITIES)]
        patience = round(random.uniform(0.3, 1.0), 2)
        hint = _HINTS[(i - 1) % len(_HINTS)]

        print(f"[{i}/{n}] building {slug!r}  hint={hint!r}")
        bundle = await build_bundle(slug, verbosity=verbosity, patience=patience, hint=hint)
        print(f"      → {len(bundle.operations)} ops  {bundle.intent_description[:60]}")
        bundles.append(bundle)

    return bundles
