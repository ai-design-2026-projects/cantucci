import json
import logging
import uuid
from typing import Any

from backend.data_access.connection import transaction
from backend.data_access.concepts.types import ConceptRow, ConceptScoreRow

log = logging.getLogger(__name__)


def create_concept(name: str, concept_type: str, definition: dict[str, Any]) -> uuid.UUID:
    """Insert a new concept and return its UUID.

    Args:
        name:         Human-readable concept name.
        concept_type: ``"linear_axis"`` or ``"prototype"``.
        definition:   Dict encoding the concept representation.

    Returns:
        UUID of the newly created concept.
    """
    with transaction() as conn:
        row = conn.execute(
            "INSERT INTO concepts (name, type, definition) VALUES (%s, %s, %s) RETURNING id",
            (name, concept_type, json.dumps(definition)),
        ).fetchone()
    concept_id: uuid.UUID = row["id"]
    log.debug("concept_created", extra={"concept_id": str(concept_id), "name": name, "type": concept_type})
    return concept_id


def upsert_concept_scores(concept_id: uuid.UUID, scores: dict[int, float]) -> None:
    """Insert or replace concept score rows for all movies in *scores*.

    Args:
        concept_id: Concept UUID.
        scores:     Dict mapping movie_id → score.
    """
    if not scores:
        return
    rows = [(concept_id, movie_id, score) for movie_id, score in scores.items()]
    with transaction() as conn:
        conn.executemany(
            """
            INSERT INTO concept_scores (concept_id, movie_id, score)
            VALUES (%s, %s, %s)
            ON CONFLICT (concept_id, movie_id) DO UPDATE SET score = EXCLUDED.score
            """,
            rows,
        )
    log.debug("concept_scores_upserted", extra={"concept_id": str(concept_id), "count": len(rows)})


def get_concept_by_name(name: str) -> ConceptRow | None:
    """Look up the most recently created concept with the given name.

    Args:
        name: Concept name to search for.

    Returns:
        ``ConceptRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, name, type, definition, created_at FROM concepts WHERE name = %s ORDER BY created_at DESC LIMIT 1",
            (name,),
        ).fetchone()
    if row is None:
        return None
    return ConceptRow.from_row(row)


def get_concept_scores(concept_id: uuid.UUID, movie_ids: list[int] | None = None) -> list[ConceptScoreRow]:
    """Return concept scores, optionally filtered to specific movies.

    Args:
        concept_id: Concept UUID.
        movie_ids:  If provided, only return scores for these IDs.

    Returns:
        List of ``ConceptScoreRow`` ordered by descending score.
    """
    with transaction() as conn:
        if movie_ids is not None:
            rows = conn.execute(
                "SELECT concept_id, movie_id, score FROM concept_scores WHERE concept_id = %s AND movie_id = ANY(%s) ORDER BY score DESC",
                (concept_id, movie_ids),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT concept_id, movie_id, score FROM concept_scores WHERE concept_id = %s ORDER BY score DESC",
                (concept_id,),
            ).fetchall()
    return [ConceptScoreRow.from_row(r) for r in rows]
