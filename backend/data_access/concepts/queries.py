import json
import logging
import uuid
from typing import Any

from backend.data_access.connection import transaction
from backend.data_access.concepts.types import ConceptAxisPointRow, ConceptRow, ConceptScoreRow

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
    log.debug(
        "concept_created",
        extra={"concept_id": str(concept_id), "concept_name": name, "concept_type": concept_type},
    )
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
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO concept_scores (concept_id, movie_id, score)
                VALUES (%s, %s, %s)
                ON CONFLICT (concept_id, movie_id) DO UPDATE SET score = EXCLUDED.score
                """,
                rows,
            )
    log.debug("concept_scores_upserted", extra={"concept_id": str(concept_id), "count": len(rows)})


def get_concept(concept_id: uuid.UUID) -> ConceptRow | None:
    """Fetch a concept row by its UUID.

    Args:
        concept_id: Concept UUID.

    Returns:
        ``ConceptRow`` if found, ``None`` otherwise.
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, name, type, definition, created_at FROM concepts WHERE id = %s",
            (concept_id,),
        ).fetchone()
    if row is None:
        return None
    return ConceptRow.from_row(row)


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


def get_conversation_axis_concepts(conversation_id: uuid.UUID) -> list[ConceptRow]:
    """Return the distinct concept axes proposed during a conversation.

    Joins the ``messages.axis_concept_id`` column (set when the coordinator
    persists an axis proposal) back to ``concepts``, deduplicating by
    concept id.  Ordering is by concept creation time ascending so the judge
    sees axes in the order they were introduced.

    Args:
        conversation_id: UUID of the conversation.

    Returns:
        List of ``ConceptRow`` ordered by ``created_at`` ascending.
        Empty when the session built no concept axes.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT ON (c.id)
                c.id, c.name, c.type, c.definition, c.created_at
            FROM concepts c
            JOIN messages m ON m.axis_concept_id = c.id
            WHERE m.conversation_id = %s
            ORDER BY c.id, c.created_at ASC
            """,
            (conversation_id,),
        ).fetchall()
    return [ConceptRow.from_row(r) for r in rows]


def get_concept_axis_points(concept_id: uuid.UUID) -> list[ConceptAxisPointRow]:
    """Return per-movie axis points enriched with movie titles, ordered by ascending score.

    Joins ``concept_scores`` with the ``movies`` table to include the display title.
    Scores are expected to be normalized to [-1, 1] (written by the cluster command
    via ``upsert_concept_scores`` after ``normalize_axis_scores``).

    Args:
        concept_id: Concept UUID.

    Returns:
        List of ``ConceptAxisPointRow`` ordered by score ascending (most negative first).
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT cs.movie_id, m.title, cs.score, COALESCE(m.vote_count, 0) AS vote_count
            FROM concept_scores cs
            JOIN movies m ON m.id = cs.movie_id
            WHERE cs.concept_id = %s
            ORDER BY cs.score ASC
            """,
            (concept_id,),
        ).fetchall()
    return [ConceptAxisPointRow.from_row(r) for r in rows]
