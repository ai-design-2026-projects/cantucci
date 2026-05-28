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
    executed_operations: list[dict],
    current_snapshot: list[dict],
    turn_number: int,
    conversation_id: uuid.UUID,
    accumulated_cost: float,
) -> OracleTurnResult:
    """Generate a single oracle reply based on the pending trajectory.

    Derives the pending operations list by subtracting executed_operations from
    ground_truth.operations. Renders the oracle prompt and calls the LLM harness
    once via the oracle model tier from eval/eval.yaml.

    Args:
        persona:              Oracle persona row (verbosity, patience).
        ground_truth:         Ground truth row with ordered operations and intent_description.
        transcript:           Full message history as ``[{"role": ..., "content": ...}]``.
        executed_operations:  Operations already executed this session (dicts with op/concept).
        current_snapshot:     Current cluster state as list of dicts with label/summary/exemplar_titles.
        turn_number:          Current 1-based oracle turn index.
        conversation_id:      Parent conversation UUID (for logging).
        accumulated_cost:     Running oracle LLM cost to check against the oracle cost limit.

    Returns:
        ``OracleTurnResult`` with oracle message, decision, rationale, session_rating, and cost.

    Raises:
        CostLimitExceeded: If accumulated cost exceeds the oracle cost limit.
        LLMParseError:     If the LLM returns an invalid payload.
    """
    harness_cfg = load_eval_harness_config()
    model = harness_cfg.oracle

    executed_set = [(op["op"], op["concept"]) for op in executed_operations]
    pending = [
        op for op in ground_truth.operations
        if (op["op"], op["concept"]) not in executed_set
    ]

    verbosity_hint = _VERBOSITY_HINTS.get(persona.verbosity, _VERBOSITY_HINTS["medium"])
    tail_size = 6
    transcript_tail = transcript[-tail_size:] if len(transcript) > tail_size else transcript

    template = _ENV.get_template("oracle_v1.j2")
    prompt = template.render(
        intent_description=ground_truth.intent_description,
        pending_operations=pending,
        executed_operations=executed_operations,
        verbosity=persona.verbosity,
        verbosity_hint=verbosity_hint,
        patience=persona.patience,
        current_snapshot=current_snapshot,
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
            "pending_ops": len(pending),
        },
    )
    return result
