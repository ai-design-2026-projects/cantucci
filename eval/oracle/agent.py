import logging
import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.data_access.eval.types import GroundTruthRow, PersonaRow
from backend.llm import llm_harness
from backend.settings import get_config_hash
from eval.config import load_eval_harness_config
from eval.oracle.types import OracleLLMResponse, OracleTurnResult

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_VERBOSITY_HINTS = {
    "terse": "one or two short sentences",
    "medium": "two to four sentences",
    "verbose": "a short paragraph of four to six sentences",
}


async def oracle_turn(
    persona: PersonaRow,
    ground_truth: GroundTruthRow,
    transcript: list[dict],
    evolution_trace: list[dict],
    current_snapshot: list[dict],
    turn_number: int,
    conversation_id: uuid.UUID,
    accumulated_cost: float,
) -> OracleTurnResult:
    """Generate a single oracle reply driven by intent and observed cluster state.

    The oracle is not shown its to-do list.  It receives the intent description, the
    current cluster state, and a compact trace of what the system has done so far,
    then decides what to say next and whether to stop.

    Args:
        persona:          Oracle persona row (verbosity, patience).
        ground_truth:     Ground truth row providing the intent description.
        transcript:       Full message history as ``[{"role": ..., "content": ...}]``.
        evolution_trace:  Compact per-turn operation trace accumulated by the runner:
                          ``[{"turn": int, "modes": [...], "concepts": [...]}]``.
        current_snapshot: Current cluster state as a list of dicts with
                          ``label``, ``summary``, and ``exemplar_titles``.
        turn_number:      Current 1-based oracle turn index.
        conversation_id:  Parent conversation UUID (for logging).
        accumulated_cost: Running oracle LLM cost to check against the oracle cost limit.

    Returns:
        ``OracleTurnResult`` with oracle message, decision, rationale, session_rating,
        and cost.

    Raises:
        CostLimitExceeded: If accumulated cost exceeds the oracle cost limit.
        LLMParseError:     If the LLM returns an invalid payload.
    """
    harness_cfg = load_eval_harness_config()
    model = harness_cfg.oracle

    verbosity_hint = _VERBOSITY_HINTS.get(persona.verbosity, _VERBOSITY_HINTS["medium"])
    tail_size = harness_cfg.runner.transcript_tail
    transcript_tail = transcript[-tail_size:] if len(transcript) > tail_size else transcript

    template = _ENV.get_template("oracle_v2.j2")
    prompt = template.render(
        intent_description=ground_truth.intent_description,
        verbosity=persona.verbosity,
        verbosity_hint=verbosity_hint,
        patience=persona.patience,
        current_snapshot=current_snapshot,
        evolution_trace=evolution_trace,
        transcript_tail=transcript_tail,
        turn_number=turn_number,
        max_turns=harness_cfg.runner.max_turns,
    )

    resp = await llm_harness.call(
        run_id="eval",
        conversation_id=str(conversation_id),
        message_id="00000000-0000-0000-0000-000000000000",
        config_hash=get_config_hash(),
        model_and_version=model.name,
        provider=model.provider,
        seed=model.seed,
        max_tokens=model.max_tokens,
        step_type="oracle_turn",
        messages=[{"role": "user", "content": prompt}],
        cost_limit_usd=model.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=model.dry_run,
        response_schema=OracleLLMResponse,
    )

    parsed: OracleLLMResponse = resp.parsed  # type: ignore[assignment]
    result = OracleTurnResult.from_llm_response(parsed, cost=resp.cost_usd)

    log.debug(
        "oracle_turn_done",
        extra={
            "conversation_id": str(conversation_id),
            "turn_number": turn_number,
            "decision": result.decision,
            "evolution_steps": len(evolution_trace),
        },
    )
    return result
