import logging
import uuid
from jinja2 import Environment, FileSystemLoader

from backend.agents.concept.parser import parse_concept
from backend.agents.concept.types import ConceptLLMResponse, ConceptRep
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

_PROMPTS_DIR = prompts_dir("concept")
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def build_concept(
    concept_name: str,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
) -> ConceptRep:
    """Parse a concept string and build its embedding-space representation.

    For linear axes: embeds the positive and negative pole descriptions, then
    computes axis = normalize(positive_centroid - negative_centroid).

    For prototypes: resolves exemplar titles to movie IDs via k-NN text search,
    fetches their fused embeddings, and computes a mean centroid.

    Args:
        concept_name:     User-supplied concept string (e.g. ``"surrealism"``).
        conversation_id:  Conversation UUID for logging.
        message_id:       Message UUID for logging.
        accumulated_cost: Running LLM cost this conversation.

    Returns:
        A ``LinearAxisRep`` or ``PrototypeRep``, each carrying the call ``cost``.

    Raises:
        ConceptParseError: If the LLM response is invalid or exemplars cannot be resolved.
    """
    cfg = get_settings()

    template = _ENV.get_template("parse_v3.j2")
    prompt = template.render(concept=concept_name)
    messages = [{"role": "user", "content": prompt}]

    resp = await llm_harness.call(
        run_id="online",
        conversation_id=str(conversation_id),
        message_id=str(message_id),
        config_hash=get_config_hash(),
        model_and_version=cfg.models.strong.name,
        provider=cfg.models.strong.provider,
        seed=cfg.models.strong.seed,
        max_tokens=cfg.models.strong.max_tokens,
        step_type="concept_agent",
        messages=messages,
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=cfg.models.strong.dry_run,
        response_schema=ConceptLLMResponse,
    )

    parsed: ConceptLLMResponse = resp.parsed  # type: ignore[assignment]
    concept = parse_concept(parsed, concept_name, cost=resp.cost_usd)

    log.info(
        "concept_built",
        extra={
            "concept": concept_name,
            "type": parsed.type,
            "cost_usd": resp.cost_usd,
        },
    )
    return concept
