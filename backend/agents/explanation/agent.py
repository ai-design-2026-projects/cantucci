import logging
import uuid
from typing import Any

from backend.agents.base import LLMAgent
from backend.agents.explanation.types import ExplanationResult
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.movies.queries import fetch_metadata, fetch_stubs
from backend.llm.types import LLMResponse

log = logging.getLogger(__name__)


class ExplanationLLMAgent(LLMAgent[ExplanationResult]):
    """Generates a natural-language explanation for a movie's cluster placement."""

    name = "explanation"
    step_type = "explanation_agent"
    model_tier = "strong"
    template_name = "explain_v2.j2"
    response_schema = None              # No response schema since the explanation is free-form text

    async def run(
        self,
        *,
        conversation_id: uuid.UUID | str,
        message_id: uuid.UUID | str,
        accumulated_cost: float,
        run_id: str = "online",
        **inputs: Any,
    ) -> ExplanationResult:
        """
        Fetch movie and cluster data before calling the LLM, with early return if not found.

        Args:
            conversation_id:  Conversation UUID for logging.
            message_id:       Message UUID for logging.
            accumulated_cost: Running LLM cost this conversation.
            run_id:           Experiment run identifier (default ``"online"``).
            **inputs:         Must include ``movie_id``, ``cluster_id``,
                              ``cluster_snapshot_id``.

        Returns:
            ``ExplanationResult`` with the explanation text.
        """
        movie_id: int = inputs["movie_id"]
        cluster_id: uuid.UUID = inputs["cluster_id"]
        cluster_snapshot_id: uuid.UUID = inputs["cluster_snapshot_id"]

        movie_rows = fetch_metadata([movie_id])
        if not movie_rows:
            return ExplanationResult(
                text=f"Movie {movie_id} not found in catalogue.",
                movie_title="Unknown",
                cluster_label="Unknown",
            )
        movie = movie_rows[0]

        cswc = get_cluster_snapshot_with_clusters(cluster_snapshot_id)
        target_cluster = next(
            (c for c in (cswc.clusters if cswc else []) if c.id == cluster_id), None
        )
        cluster_label = target_cluster.label if target_cluster else "Unknown"
        cluster_summary = target_cluster.summary if target_cluster else None
        exemplar_ids = target_cluster.exemplar_movie_ids[:5] if target_cluster else []

        exemplar_stubs = fetch_stubs(exemplar_ids)
        exemplar_titles = [s.title for s in exemplar_stubs if s.id != movie_id][:4]

        return await super().run(
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
            run_id=run_id,
            movie=movie,
            cluster_label=cluster_label,
            cluster_summary=cluster_summary,
            exemplar_titles=exemplar_titles,
            movie_id=movie_id,
            cluster_id=cluster_id,
        )

    async def render_kwargs(self, **inputs: Any) -> dict[str, Any]:
        movie = inputs["movie"]
        return {
            "movie_title": movie.title,
            "release_year": movie.release_year,
            "overview": movie.overview,
            "genres": movie.genres,
            "director": movie.director,
            "cluster_label": inputs["cluster_label"],
            "cluster_summary": inputs["cluster_summary"],
            "exemplar_titles": inputs["exemplar_titles"],
        }

    def build_result(self, resp: LLMResponse, **inputs: Any) -> ExplanationResult:
        movie = inputs["movie"]
        log.info(
            "explanation_generated",
            extra={
                "movie_id": inputs["movie_id"],
                "cluster_id": str(inputs["cluster_id"]),
            },
        )
        return ExplanationResult.from_llm_response(
            resp.content,
            movie_title=movie.title,
            cluster_label=inputs["cluster_label"],
            cost=resp.cost_usd,
        )


agent = ExplanationLLMAgent()
