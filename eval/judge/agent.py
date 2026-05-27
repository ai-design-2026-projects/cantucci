import hashlib
import logging
import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.conversations.queries import get_conversation, get_messages
from backend.data_access.movies.queries import fetch_stubs
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings
from eval.judge.types import JudgeLLMResponse, JudgeResult

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def judge_conversation(
    conversation_id: uuid.UUID,
    accumulated_cost: float,
    ground_truth_description: str | None = None,
) -> JudgeResult:
    """Score a completed conversation on four quality dimensions.

    Reads the conversation transcript and final cluster snapshot from the
    database, renders the judge prompt, and calls the LLM harness once.
    The rendered prompt's SHA-256 hash is included in the result for audit.

    Args:
        conversation_id:         UUID of the completed conversation to judge.
        accumulated_cost:        Running LLM cost to check against the limit.
        ground_truth_description: Optional taste description shown to the oracle
                                  (included in the judge prompt for fidelity
                                  assessment; never the hidden target set).

    Returns:
        ``JudgeResult`` with validated per-dimension scores and prompt hash.

    Raises:
        CostLimitExceeded: If accumulated cost exceeds the conversation limit.
        LLMParseError:     If the LLM response is missing a required dimension
                           or contains a score outside [1, 5].
    """
    cfg = get_settings()
    model = cfg.models.strong

    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"conversation {conversation_id} not found")

    messages = get_messages(conversation_id, limit=1000)
    transcript = [{"role": m.role, "content": m.content} for m in messages]

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
        ground_truth_description=ground_truth_description,
        transcript=transcript,
        clusters=clusters_info,
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
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=model.dry_run,
        response_schema=JudgeLLMResponse,
    )

    parsed: JudgeLLMResponse = resp.parsed  # type: ignore[assignment]
    result = JudgeResult.from_llm_response(
        parsed,
        expected_dimensions=cfg.eval.judge_dimensions,
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
