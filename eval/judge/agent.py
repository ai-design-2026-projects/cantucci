import hashlib
import logging
import uuid
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.conversations.queries import get_conversation, get_messages
from backend.data_access.eval.queries import list_turn_intents
from backend.data_access.movies.queries import fetch_stubs
from backend.llm import llm_harness
from backend.settings import get_config_hash
from eval.config import load_eval_harness_config
from eval.judge.types import JudgeLLMResponse, JudgeResult

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def judge_conversation(
    conversation_id: uuid.UUID,
    ground_truth_intent_description: str | None,
    ground_truth_operations: list[dict] | None,
) -> JudgeResult:
    """Score a completed conversation on five quality dimensions.

    Offline operation: always starts at accumulated_cost=0.0 and uses the
    judge-specific cost limit from eval/eval.yaml, not the runtime conversation
    limit.  Reads the transcript, per-turn intent rows, and final cluster
    snapshot from the database, then calls the LLM harness once.

    Args:
        conversation_id:                 UUID of the completed conversation to judge.
        ground_truth_intent_description: Intent description from the GT (shown to judge).
        ground_truth_operations:         Ordered list of GT ``{op, concept}`` dicts.

    Returns:
        ``JudgeResult`` with validated per-dimension scores and prompt hash.

    Raises:
        FileNotFoundError: If eval/eval.yaml is missing.
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

    turn_action_log = []
    for turn_num in sorted(turns_by_number):
        rows = turns_by_number[turn_num]
        turn_action_log.append({
            "modes": [r.mode for r in rows],
            "concepts": [r.concept for r in rows],
            "confidence": min(r.confidence for r in rows),
            "clarifier_fired": any(r.clarifier_fired for r in rows),
            "suggestion": None,
            "explanation": None,
        })

    clusters_info: list[dict] = []
    if conversation.current_cluster_snapshot_id is not None:
        snapshot_with_clusters = get_cluster_snapshot_with_clusters(conversation.current_cluster_snapshot_id)
        if snapshot_with_clusters is not None:
            for cluster in snapshot_with_clusters.clusters:
                stubs = fetch_stubs(cluster.exemplar_movie_ids[:5]) if cluster.exemplar_movie_ids else []
                exemplar_titles = [f"{s.title} ({s.release_year or '?'})" for s in stubs]
                clusters_info.append({
                    "label": cluster.label,
                    "summary": cluster.summary,
                    "exemplar_titles": exemplar_titles,
                })

    template = _ENV.get_template("judge_v1.j2")
    prompt = template.render(
        intent_description=ground_truth_intent_description or "(not provided)",
        ground_truth_operations=ground_truth_operations or [],
        transcript=transcript,
        turn_action_log=turn_action_log,
        final_clusters=clusters_info,
    )

    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    log.debug("judge_prompt_rendered", extra={"conversation_id": str(conversation_id), "prompt_hash": prompt_hash[:8]})

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
        expected_dimensions=harness_cfg.scorer.dimensions,
        cost=resp.cost_usd,
        prompt_hash=prompt_hash,
    )

    log.info(
        "judge_conversation_done",
        extra={
            "conversation_id": str(conversation_id),
            "prompt_hash": prompt_hash[:8],
            "scores": {dim: score for dim, (score, _) in result.scores.items()},
        },
    )
    return result
