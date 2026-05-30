import numpy as np

from backend.agents.concept.types import ConceptLLMResponse, LinearAxisRep
from backend.exceptions import ConceptParseError


def build_linear_axis(parsed: ConceptLLMResponse, concept_name: str, cost: float) -> LinearAxisRep:
    """
    Build a LinearAxisRep from a validated LLM response.

    - Embeds all positive-pole descriptions and all negative-pole descriptions,
    computes a per-pole centroid (averaging multiple descriptions is more robust to LLM noise);
    - axis = normalize(pos_centroid - neg_centroid);

    The encoder is chosen by ``parsed.space``:
    - ``"semantic"`` → BGE sentence-transformer (``core.text_encoder.embed_texts``);
      axis lives in the same space as ``text_embedding``.
    - ``"visual"`` → CLIP text tower (``core.image_encoder.encode_texts``); axis lives
      in the same space as ``trailer_embedding``. Visual descriptions must be short
      phrases to stay within CLIP's 77-token context limit.
    
    Args:
        parsed:       Validated wire response with ``positive_descriptions`` and
                      ``negative_descriptions`` set.
        concept_name: Human-readable concept label for the result.
        cost:         LLM cost in USD to carry on the result.
    Raises:
        ConceptParseError: If description lists are empty, embeddings fail, or axis has zero norm.
    """
    # Basic validation before expensive embedding calls
    if not parsed.positive_descriptions or not parsed.negative_descriptions:
        raise ConceptParseError(concept_name)
    
    # Import the embedding functions based on the concept space
    if parsed.space == "visual":
        from core.image_encoder import encode_texts as embed_fn
    else:
        from core.text_encoder import embed_texts as embed_fn  # type: ignore[assignment]

    # Embed descriptions and compute centroid
    pos_embs = embed_fn(parsed.positive_descriptions)
    neg_embs = embed_fn(parsed.negative_descriptions)
    pos_centroid = pos_embs.mean(axis=0)
    neg_centroid = neg_embs.mean(axis=0)

    # The axis is the normalized vector from the negative centroid to the positive centroid
    axis = pos_centroid - neg_centroid
    norm = np.linalg.norm(axis)
    if norm == 0:
        raise ConceptParseError(concept_name)
    axis = (axis / norm).astype(np.float32)
    return LinearAxisRep(
        concept_name=concept_name,
        space=parsed.space,
        axis_vector=axis,
        cost=cost,
        positive_label=parsed.positive_label,
        negative_label=parsed.negative_label,
    )
