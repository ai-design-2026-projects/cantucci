import logging
import random
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.data_access.evaluation.types import GroundTruthRow, PersonaRow
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings
from eval.oracle.types import OracleLLMResponse, OracleTurnResult

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_VERBOSITY_HINTS = {
    "terse": "one or two short sentences",
    "medium": "two to four sentences",
    "verbose": "a short paragraph of four to six sentences",
}

_MIN_ACCEPT_TURN_FROM_DECISIVENESS = {
    range(0, 20): 10,
    range(20, 40): 7,
    range(40, 60): 5,
    range(60, 80): 3,
    range(80, 101): 1,
}


def _min_accept_turn(decisiveness: float) -> int:
    """Derive the earliest turn the oracle is willing to accept.

    Args:
        decisiveness: Float in [0, 1]; 1.0 = accepts immediately.

    Returns:
        1-based minimum turn number for acceptance.
    """
    pct = int(decisiveness * 100)
    for rng, turn in _MIN_ACCEPT_TURN_FROM_DECISIVENESS.items():
        if pct in rng:
            return turn
    return 1


def _seeded_roll(probability: float, persona_slug: str, gt_slug: str, seed: int, turn_number: int, salt: str) -> bool:
    """Deterministic Bernoulli roll keyed on session identifiers.

    Uses a seeded RNG so the same oracle/ground-truth/seed/turn triple always
    produces the same outcome, making simulated sessions reproducible.

    Args:
        probability:  Probability of returning True.
        persona_slug: Persona identifier.
        gt_slug:      Ground truth identifier.
        seed:         Session RNG seed.
        turn_number:  Current turn index (1-based).
        salt:         Extra string to differentiate drift vs contradiction rolls.

    Returns:
        True with the given probability.
    """
    rng = random.Random(f"{persona_slug}:{gt_slug}:{seed}:{turn_number}:{salt}")
    return rng.random() < probability


async def oracle_turn(
    persona: PersonaRow,
    ground_truth: GroundTruthRow,
    transcript: list[dict],
    system_message: str,
    turn_number: int,
    seed: int,
    conversation_id: str,
    accumulated_cost: float,
) -> OracleTurnResult:
    """Generate a single oracle reply and classify its intent.

    The oracle sees the ground truth's taste description (never the hidden
    target film set). Behavioural modifiers (drift, contradiction) are rolled
    deterministically so reruns of the same session reproduce the same sequence.

    The acceptance gate is applied after the LLM emits "accept": if the oracle
    has not yet reached its minimum-turn threshold, the intent is overridden to
    "continue".

    Args:
        persona:         Oracle persona row.
        ground_truth:    Ground truth row (description shown; spec/targets hidden).
        transcript:      List of ``{"role": ..., "content": ...}`` dicts so far.
        system_message:  The system's latest reply that the oracle is responding to.
        turn_number:     Current 1-based oracle turn index.
        seed:            Session RNG seed for behavioural reproducibility.
        conversation_id: Parent conversation UUID string (for logging).
        accumulated_cost: Running LLM cost to check against the limit.

    Returns:
        ``OracleTurnResult`` with oracle message, intent, and call cost.

    Raises:
        CostLimitExceeded: If accumulated cost exceeds the conversation limit.
        LLMParseError:     If the LLM returns an unrecognised intent value.
    """
    cfg = get_settings()

    injected_tangent = _seeded_roll(
        persona.drift_probability, persona.slug, ground_truth.slug, seed, turn_number, "drift"
    )
    injected_contradiction = _seeded_roll(
        persona.contradiction_rate, persona.slug, ground_truth.slug, seed, turn_number, "contradiction"
    )

    verbosity_hint = _VERBOSITY_HINTS.get(persona.verbosity, _VERBOSITY_HINTS["medium"])
    min_turn = _min_accept_turn(persona.decisiveness)

    template = _ENV.get_template("oracle_v1.j2")
    prompt = template.render(
        taste_description=ground_truth.description,
        verbosity=persona.verbosity,
        verbosity_hint=verbosity_hint,
        decisiveness=persona.decisiveness,
        min_accept_turn=min_turn,
        injected_tangent=injected_tangent,
        injected_contradiction=injected_contradiction,
        transcript=transcript,
        system_message=system_message,
    )

    model = cfg.models.strong
    resp = await llm_harness.call(
        run_id="eval",
        conversation_id=conversation_id,
        message_id="00000000-0000-0000-0000-000000000000",
        config_hash=get_config_hash(),
        model_and_version=model.name,
        provider=model.provider,
        seed=model.seed,
        max_tokens=model.max_tokens,
        step_type="oracle_turn",
        messages=[{"role": "user", "content": prompt}],
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=model.dry_run,
        response_schema=OracleLLMResponse,
    )

    parsed: OracleLLMResponse = resp.parsed  # type: ignore[assignment]
    result = OracleTurnResult.from_llm_response(parsed, cost=resp.cost_usd)

    if result.intent == "accept" and turn_number < min_turn:
        log.debug(
            "oracle_acceptance_gate_blocked",
            extra={"turn_number": turn_number, "min_accept_turn": min_turn},
        )
        result = OracleTurnResult(message=result.message, intent="continue", cost=result.cost)

    log.debug(
        "oracle_turn_done",
        extra={"conversation_id": conversation_id, "turn_number": turn_number, "intent": result.intent},
    )
    return result
