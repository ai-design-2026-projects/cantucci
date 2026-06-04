import uuid

from fastapi import APIRouter

from backend.data_access.concepts.queries import get_concept, get_concept_axis_points
from backend.exceptions import ConceptNotFound
from backend.routers.dto.concepts.dtos import AxisDistributionDto, AxisPointDto

router = APIRouter(prefix="/concepts", tags=["concepts"])


@router.get("/{concept_id}/axis", response_model=AxisDistributionDto)
def get_concept_axis_endpoint(concept_id: uuid.UUID) -> AxisDistributionDto:
    """Return the distribution of movies along a concept's linear axis.

    Scores are normalised to [-1, 1] via min-max over the full scored set.
    The positive and negative pole labels (e.g. "action-packed" / "meditative")
    are included so the frontend can annotate the axis ends without a second call.
    The endpoint is public — no auth required, consistent with cluster-snapshot endpoints.

    Args:
        concept_id: UUID of the concept.

    Returns:
        ``AxisDistributionDto`` with per-movie scores ordered by ascending score,
        plus the concept name and pole labels.

    Raises:
        ConceptNotFound: If the concept_id does not exist.
    """
    concept = get_concept(concept_id)
    if concept is None:
        raise ConceptNotFound(concept_id)

    points = get_concept_axis_points(concept_id)
    return AxisDistributionDto(
        concept_id=concept.id,
        concept_name=concept.name,
        positive_label=concept.definition.get("positive_label", ""),
        negative_label=concept.definition.get("negative_label", ""),
        points=[AxisPointDto(movie_id=p.movie_id, title=p.title, score=p.score, vote_count=p.vote_count) for p in points],
    )
