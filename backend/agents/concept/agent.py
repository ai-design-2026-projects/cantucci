import logging
import uuid

import numpy as np
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from backend.agents.concept.types import ConceptRep, LinearAxisRep, PrototypeRep
from backend.data_access.movies.queries import fetch_text_embeddings, vector_search
from backend.exceptions import ConceptParseError
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

_PROMPTS_DIR = prompts_dir("concept")
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


class _ConceptLLMResponse(BaseModel):
    """Structured output expected from the concept parsing LLM call."""
    type: str
    positive_description: str | None = None
    negative_description: str | None = None
    exemplar_titles: list[str] = []


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
        concept_name:    User-supplied concept string (e.g. ``"surrealism"``).
        conversation_id: Conversation UUID for logging.
        message_id:      Message UUID for logging.
        accumulated_cost: Running LLM cost this conversation.

    Returns:
        A ``LinearAxisRep`` or ``PrototypeRep``.

    Raises:
        ConceptParseError: If the LLM response is invalid or exemplars cannot be resolved.
    """
    from core.text_encoder import embed_texts

    cfg = get_settings()

    template = _ENV.get_template("parse_v1.j2")
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
        response_schema=_ConceptLLMResponse,
    )
    parsed: _ConceptLLMResponse = resp.parsed  # type: ignore[assignment]

    if parsed.type == "linear_axis":
        if not parsed.positive_description or not parsed.negative_description:
            raise ConceptParseError(concept_name)
        pos_emb = embed_texts([parsed.positive_description])[0]
        neg_emb = embed_texts([parsed.negative_description])[0]
        axis = pos_emb - neg_emb
        norm = np.linalg.norm(axis)
        if norm == 0:
            raise ConceptParseError(concept_name)
        axis = (axis / norm).astype(np.float32)
        log.info("concept_built_axis", extra={"concept": concept_name})
        return LinearAxisRep(concept_name=concept_name, axis_vector=axis)

    if parsed.type == "prototype":
        if not parsed.exemplar_titles:
            raise ConceptParseError(concept_name)

        exemplar_ids: list[int] = []
        for title in parsed.exemplar_titles:
            hits = vector_search(embed_texts([title])[0], k=1)
            if hits:
                exemplar_ids.append(hits[0].movie_id)

        if not exemplar_ids:
            raise ConceptParseError(concept_name)

        emb_map = fetch_text_embeddings(exemplar_ids)
        if not emb_map:
            raise ConceptParseError(concept_name)

        vecs = np.array(list(emb_map.values()), dtype=np.float32)
        centroid = vecs.mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = (centroid / norm).astype(np.float32)

        log.info("concept_built_prototype", extra={"concept": concept_name, "n_exemplars": len(exemplar_ids)})
        return PrototypeRep(concept_name=concept_name, centroid=centroid, exemplar_movie_ids=list(emb_map.keys()))

    raise ConceptParseError(concept_name)


def score_movies(
    concept: ConceptRep,
    movie_ids: list[int],
    embeddings: dict[int, list[float]],
) -> dict[int, float]:
    """Score a set of movies against a concept representation.

    For ``LinearAxisRep``: score = dot(movie_embedding, axis_vector).
    For ``PrototypeRep``: score = cosine_similarity(movie_embedding, centroid).

    Args:
        concept:    The concept representation to score against.
        movie_ids:  List of TMDB IDs to score.
        embeddings: Pre-fetched embedding dict {movie_id: [float, ...]}.

    Returns:
        Dict mapping movie_id → score. Movies missing from embeddings are omitted.
    """
    scores: dict[int, float] = {}
    for mid in movie_ids:
        if mid not in embeddings:
            continue
        vec = np.array(embeddings[mid], dtype=np.float32)
        if isinstance(concept, LinearAxisRep):
            scores[mid] = float(np.dot(vec, concept.axis_vector))
        else:
            scores[mid] = float(np.dot(vec, concept.centroid))
    return scores
