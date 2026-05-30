import numpy as np

from backend.agents.concept.types import (
    ConceptLLMResponse,
    ConceptRep,
    LinearAxisRep,
    PrototypeRep,
)
from backend.data_access.movies.queries import fetch_text_embeddings, vector_search
from backend.exceptions import ConceptParseError


def build_linear_axis(
    parsed: ConceptLLMResponse,
    concept_name: str,
    cost: float,
    embedding_space: str = "text",
) -> LinearAxisRep:
    """Build a LinearAxisRep from a validated LLM response.

    Embeds all positive-pole sentences and all negative-pole sentences, computes
    a per-pole centroid, then axis = normalize(pos_centroid - neg_centroid).
    Averaging multiple sentences per pole produces a more stable direction than
    relying on a single description.

    Currently only ``"text"`` is supported as an embedding space because the
    descriptions are natural-language sentences embedded via the text encoder.
    Visual embedding spaces (``"trailer"``) require a different axis-building
    strategy (embedding exemplar frames rather than text descriptions) and are
    not yet implemented — the parameter is wired so that ``LinearAxisRep`` is
    self-describing and ``_propose_concept_axis`` can load the right embeddings
    for scoring without hardcoding the modality.

    Args:
        parsed:          Validated wire response with ``positive_descriptions`` and
                         ``negative_descriptions`` set (assumed type == "linear_axis").
        concept_name:    Human-readable concept label for the result.
        cost:            LLM cost in USD to carry on the result.
        embedding_space: Modality key the axis will live in. Defaults to ``"text"``.

    Raises:
        ConceptParseError: If description lists are empty, embeddings fail, or axis has zero norm.
    """
    from core.text_encoder import embed_texts

    if not parsed.positive_descriptions or not parsed.negative_descriptions:
        raise ConceptParseError(concept_name)

    pos_embs = embed_texts(parsed.positive_descriptions)
    neg_embs = embed_texts(parsed.negative_descriptions)
    pos_centroid = pos_embs.mean(axis=0)
    neg_centroid = neg_embs.mean(axis=0)
    axis = pos_centroid - neg_centroid
    norm = np.linalg.norm(axis)
    if norm == 0:
        raise ConceptParseError(concept_name)
    axis = (axis / norm).astype(np.float32)
    return LinearAxisRep(
        concept_name=concept_name,
        axis_vector=axis,
        embedding_space=embedding_space,
        cost=cost,
        positive_label=parsed.positive_label,
        negative_label=parsed.negative_label,
    )


def build_prototype(parsed: ConceptLLMResponse, concept_name: str, cost: float) -> PrototypeRep:
    """Build a PrototypeRep from a validated LLM response.

    Resolves exemplar titles to movie IDs via k-NN text search, fetches their
    embeddings, and computes a mean centroid.

    Args:
        parsed:       Validated wire response with ``exemplar_titles`` populated
                      (assumed type == "prototype").
        concept_name: Human-readable concept label for the result.
        cost:         LLM cost in USD to carry on the result.

    Raises:
        ConceptParseError: If no exemplar titles, no IDs resolve, or no embeddings found.
    """
    from core.text_encoder import embed_texts

    if not parsed.exemplar_titles:
        raise ConceptParseError(concept_name)

    title_embs = embed_texts(parsed.exemplar_titles)
    exemplar_ids: list[int] = []
    for emb in title_embs:
        hits = vector_search(emb, k=1)
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

    return PrototypeRep(
        concept_name=concept_name,
        centroid=centroid,
        exemplar_movie_ids=list(emb_map.keys()),
        cost=cost,
    )


def parse_concept(parsed: ConceptLLMResponse, concept_name: str, cost: float) -> ConceptRep:
    """Dispatch on the LLM response type discriminator and build the correct ConceptRep.

    Args:
        parsed:       Validated wire response with ``type`` set to ``"linear_axis"``
                      or ``"prototype"``.
        concept_name: Human-readable concept label.
        cost:         LLM cost in USD to carry on the result.

    Raises:
        ConceptParseError: If the type discriminator is unrecognised.
    """
    if parsed.type == "linear_axis":
        return build_linear_axis(parsed, concept_name, cost)
    if parsed.type == "prototype":
        return build_prototype(parsed, concept_name, cost)
    raise ConceptParseError(concept_name)
