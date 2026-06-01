import hashlib
import logging
import uuid
from collections import defaultdict

from jinja2 import Environment, FileSystemLoader

from backend.data_access.concepts.queries import get_concept_axis_points, get_conversation_axis_concepts
from backend.data_access.conversations.queries import get_conversation, get_messages
from backend.data_access.eval.queries import list_turn_intents
from backend.llm import llm_harness
from backend.settings import get_config_hash
from eval.config import eval_prompts_dir, load_eval_harness_config
from eval.judge.types import AxisConceptContext, JudgeLLMResponse, JudgeResult
from eval.runtime.snapshot import build_cluster_info

log = logging.getLogger(__name__)

_ENV = Environment(loader=FileSystemLoader(str(eval_prompts_dir("judge"))), autoescape=False)


async def judge_conversation(
    conversation_id: uuid.UUID,
    ground_truth_intent_description: str | None,
    ground_truth_operations: list[dict] | None,
) -> JudgeResult:
    """Score a completed conversation on quality dimensions.

    Offline operation: always starts at ``accumulated_cost=0.0`` and uses the
    judge-specific cost limit from ``eval/eval.yaml``.  Reads the transcript,
    per-turn intent rows, and final cluster snapshot from the database, then
    calls the LLM harness once.

    Uses ``judge_v5.j2``, which has conditional blocks for three optional
    dimensions: ``concept_axis_quality``, ``explanation_quality``, and
    ``suggestion_meaningfulness`` — no dual-template branching.

    Optional dimensions are included only when the relevant signal is present:
    ``concept_axis_quality`` when ≥1 concept axis was built; ``explanation_quality``
    when at least one turn used the ``explain`` dialogue mode; and
    ``suggestion_meaningfulness`` when at least one assistant message carried a
    non-null suggestion text.

    Args:
        conversation_id:                 UUID of the completed conversation to judge.
        ground_truth_intent_description: Intent description from the GT (shown to judge).
        ground_truth_operations:         Ordered list of GT ``{op, concept, ...}`` dicts.

    Returns:
        ``JudgeResult`` with validated per-dimension scores and prompt hash.

    Raises:
        ValueError:        If the conversation is not found.
        FileNotFoundError: If ``eval/eval.yaml`` is missing.
        LLMParseError:     If the LLM response is missing a required dimension
                           or contains a score outside [1, 5].
    """
    harness_cfg = load_eval_harness_config()
    model = harness_cfg.judge

    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"conversation {conversation_id} not found")

    messages = get_messages(conversation_id, limit=1000)
    transcript = [{"role": m.role, "content": m.content} for m in messages]

    turn_intents = list_turn_intents(conversation_id)

    turns_by_number: dict[int, list] = defaultdict(list)
    for ti in turn_intents:
        turns_by_number[ti.turn_number].append(ti)

    assistant_messages = [m for m in messages if m.role == "assistant"]

    turn_action_log = []
    for turn_idx, turn_num in enumerate(sorted(turns_by_number)):
        rows = turns_by_number[turn_num]
        suggestion_text = (
            assistant_messages[turn_idx].suggestion
            if turn_idx < len(assistant_messages)
            else None
        )
        turn_action_log.append({
            "modes": [r.mode for r in rows],
            "concepts": [r.concept for r in rows],
            "confidence": min(r.confidence for r in rows),
            "clarifier_fired": any(r.clarifier_fired for r in rows),
            "suggestion": suggestion_text,
            "explanation": any(r.mode == "explain" for r in rows),
        })

    has_explanation = any(t["explanation"] for t in turn_action_log)
    has_suggestion = any(bool(t["suggestion"]) for t in turn_action_log)

    exemplar_k = harness_cfg.scorer.exemplar_k
    clusters_info: list[dict] = []
    if conversation.current_cluster_snapshot_id is not None:
        clusters_info = build_cluster_info(conversation.current_cluster_snapshot_id, exemplar_k=exemplar_k)

    pole_k = harness_cfg.scorer.pole_sample_k
    axis_contexts: list[AxisConceptContext] = []
    for concept_row in get_conversation_axis_concepts(conversation_id):
        defn = concept_row.definition
        points = get_concept_axis_points(concept_row.id)
        high_pole_films = [p.title for p in reversed(points[-pole_k:])]
        low_pole_films = [p.title for p in points[:pole_k]]
        axis_contexts.append(AxisConceptContext(
            concept_name=defn.get("concept_name", concept_row.name),
            positive_label=defn.get("positive_label", ""),
            negative_label=defn.get("negative_label", ""),
            space=defn.get("space", "semantic"),
            high_pole_films=high_pole_films,
            low_pole_films=low_pole_films,
        ))

    has_axes = len(axis_contexts) > 0
    dimension_present = {
        "concept_axis_quality": has_axes,
        "explanation_quality": has_explanation,
        "suggestion_meaningfulness": has_suggestion,
    }
    effective_dimensions = [
        d for d in harness_cfg.scorer.dimensions
        if dimension_present.get(d, True)
    ]

    template = _ENV.get_template("judge_v5.j2")
    prompt = template.render(
        intent_description=ground_truth_intent_description or "(not provided)",
        ground_truth_operations=ground_truth_operations or [],
        transcript=transcript,
        turn_action_log=turn_action_log,
        final_clusters=clusters_info,
        axis_contexts=axis_contexts,
        has_explanation=has_explanation,
        has_suggestion=has_suggestion,
    )

    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    log.debug(
        "judge_prompt_rendered",
        extra={"conversation_id": str(conversation_id), "prompt_hash": prompt_hash[:8]},
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
        step_type="judge",
        messages=[{"role": "user", "content": prompt}],
        cost_limit_usd=model.cost_limit_usd,
        accumulated_cost_usd=0.0,
        dry_run=model.dry_run,
        response_schema=JudgeLLMResponse,
    )

    parsed: JudgeLLMResponse = resp.parsed  # type: ignore[assignment]
    result = JudgeResult.from_llm_response(
        parsed,
        expected_dimensions=effective_dimensions,
        cost=resp.cost_usd,
        prompt_hash=prompt_hash,
    )

    for dim, (score, rationale) in result.scores.items():
        log.debug(
            "judge_dimension",
            extra={
                "conversation_id": str(conversation_id),
                "dimension": dim,
                "score": score,
                "rationale": rationale,
            },
        )

    log.info(
        "judge_conversation_done",
        extra={
            "conversation_id": str(conversation_id),
            "prompt_hash": prompt_hash[:8],
            "has_axes": has_axes,
            "has_explanation": has_explanation,
            "has_suggestion": has_suggestion,
            "scores": {dim: score for dim, (score, _) in result.scores.items()},
        },
    )
    return result
