"""LLM-as-judge post-session scoring and objective metric computation.

For each completed eval session the judge:
1. Computes objective metrics (Precision@K, Recall@K, NDCG@K, avg cognitive
   load) from the session DTO and the full ground truth, then writes a
   ``session_metrics`` row.
2. Scores three subjective dimensions (1–5) using dedicated versioned prompt
   templates, then writes a ``judge_scores`` row per dimension.
    
    Subjective dimensions:
    - clustering_coherence: How coherent and well-defined is the converged cluster?
    - question_quality:     How effective and targeted were the clarifying questions?
    - profile_fidelity:     How well does the final recommendation match the persona's taste?

    Each dimension uses a dedicated versioned prompt template.  The judge_prompt_hash
    stored in judge_scores is the SHA-256 of the *rendered* prompt (not the template),
    so different persona descriptions produce different hashes and all scoring variations
    are auditable.

The judge sees:
- The neutral ground-truth description (NOT gt_movie_ids).
- The converged cluster name and description.
- The top-K recommended film titles.
- The full turn-by-turn conversation transcript.

The judge does NOT see the oracle persona's communication-style traits — only the
taste content it was supposed to find.
"""

import hashlib
import logging
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from pydantic import BaseModel

from backend.api.eval import upsert_session_metrics, write_judge_score
from backend.llm.prompts import make_prompt_loader
from backend.routers.dtos import SessionDto, TurnDto
from eval.shared.ground_truths import GroundTruth
from eval.shared.llm_gateway import LLMGateway
from eval.judge.metrics import cognitive_load, ndcg_at_k, precision_at_k, recall_at_k

log = logging.getLogger(__name__)

_DIMENSIONS = ("clustering_coherence", "question_quality", "profile_fidelity")


class _JudgeOutput(BaseModel):
    """Expected JSON output from the LLM judge.
    Attributes:
        score:     Integer 1–5.
        rationale: One-sentence justification.
    """
    score: int
    rationale: str


class Judge:
    """
    Evaluation coordinator for completed eval sessions.

    Computes objective metrics, writes session_metrics, runs the LLM judge
    for three subjective dimensions, and writes judge_scores.  One instance
    is shared across all sessions in a run.
    Attributes:
        _llm:         LLM gateway instance for judge calls.
        _prompts_dir: Path to ``eval/judge/prompts/``.
        _k:           Rank cutoff for objective metrics (Precision@K, etc.).
    """

    def __init__(self, llm: LLMGateway, prompts_dir: Path, k: int) -> None:
        """Initialise the judge.

        Args:
            llm:         LLM gateway (uses the ``judge`` budget portion).
            prompts_dir: Path to ``eval/judge/prompts/``.
            k:           Rank cutoff applied to all @K metrics.
        """
        self._llm = llm
        self._load_prompt = make_prompt_loader(prompts_dir)
        self._k = k

    async def score_session(
        self,
        session: SessionDto,
        gt: GroundTruth,
        run_id: str | UUID = "eval",
        converged: bool = False,
        turns_to_convergence: int | None = None,
        explicit_acceptance: bool = False,
        drift_events: int = 0,
        total_input_tokens: int = 0,
        total_output_tokens: int = 0,
        total_cost_usd: Decimal = Decimal("0"),
    ) -> None:
        """Score a completed session: write session_metrics and judge_scores.

        Computes objective metrics (Precision@K, Recall@K, NDCG@K, avg cognitive
        load) from the session DTO and ground truth, writes a session_metrics row,
        then runs the LLM judge over the three subjective dimensions.  Skips LLM
        scoring for abandoned sessions (no converged turn).

        Args:
            session:              Full SessionDto fetched after session completion.
            gt:                   Full ground truth (description for LLM prompts,
                                  gt_movie_ids for objective metrics).
            run_id:               Eval run UUID for log correlation.
            converged:            Whether the session reached convergence.
            turns_to_convergence: Turn number when convergence was declared.
            explicit_acceptance:  True if convergence was triggered by oracle accept.
            drift_events:         Count of preference drift events.
            total_input_tokens:   Sum of input tokens across the session.
            total_output_tokens:  Sum of output tokens across the session.
            total_cost_usd:       Estimated session API cost.
        """
        loads = [cognitive_load(t) for t in session.turns]
        avg_cognitive_load = sum(loads) / len(loads) if loads else None

        final_turn = session.last_turn_with_recommendation()
        recommended_ids = (
            [f.id for f in final_turn.recommendation.films]
            if final_turn and final_turn.recommendation
            else []
        )

        p_at_k = precision_at_k(recommended_ids, gt.gt_movie_ids, self._k) if recommended_ids else None
        r_at_k = recall_at_k(recommended_ids, gt.gt_movie_ids, self._k) if recommended_ids else None
        n_at_k = ndcg_at_k(recommended_ids, gt.gt_movie_ids, self._k) if recommended_ids else None

        upsert_session_metrics(
            session_id=session.session_id,
            converged=converged,
            turns_to_convergence=turns_to_convergence,
            avg_cognitive_load=avg_cognitive_load,
            explicit_acceptance=explicit_acceptance,
            drift_events=drift_events,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_cost_usd=total_cost_usd,
            precision_at_k=p_at_k,
            recall_at_k=r_at_k,
            ndcg_at_k=n_at_k,
        )

        log.info(
            "judge metrics session_id=%s p@k=%s r@k=%s ndcg@k=%s",
            session.session_id,
            f"{p_at_k:.3f}" if p_at_k is not None else "None",
            f"{r_at_k:.3f}" if r_at_k is not None else "None",
            f"{n_at_k:.3f}" if n_at_k is not None else "None",
        )
        converged_turn = session.converged_turn()
        if converged_turn is None:
            log.info(
                "judge: skipping llm scoring for abandoned session session_id=%s", session.session_id
            )
            return

        cluster_name = ""
        cluster_description = ""
        film_titles: list[str] = []
        if converged_turn.recommendation:
            cluster_name = converged_turn.recommendation.cluster.name
            cluster_description = converged_turn.recommendation.cluster.description or ""
            film_titles = [f.title for f in converged_turn.recommendation.films]

        transcript = session.transcript()

        for dimension in _DIMENSIONS:
            await self._score_dimension(
                dimension=dimension,
                session=session,
                gt_description=gt.description,
                cluster_name=cluster_name,
                cluster_description=cluster_description,
                film_titles=film_titles,
                transcript=transcript,
                run_id=run_id,
            )

    async def _score_dimension(
        self,
        *,
        dimension: str,
        session: SessionDto,
        gt_description: str,
        cluster_name: str,
        cluster_description: str,
        film_titles: list[str],
        transcript: str,
        run_id: str | UUID,
    ) -> None:
        """
        Score one dimension and write a ``judge_scores`` row.
        Args:
            dimension:           One of the three scoring dimensions.
            session:             Full session DTO.
            gt_description:      Neutral taste description for the ground truth.
            cluster_name:        Converged cluster name.
            cluster_description: Converged cluster description.
            film_titles:         Final recommended film titles.
            transcript:          Plain-text turn-by-turn transcript.
            run_id:              Eval run UUID for logging.
        """
        prompt_name = f"judge_{dimension}_v1"
        rendered, prompt_hash = self._load_prompt(
            prompt_name,
            {
                "gt_description": gt_description,
                "cluster_name": cluster_name,
                "cluster_description": cluster_description,
                "film_titles": film_titles,
                "transcript": transcript,
            },
        )
        full_prompt_hash = hashlib.sha256(rendered.encode()).hexdigest()
        reply = await self._llm.call(
            messages=[
                {"role": "system", "content": "You are an expert movie recommendation system evaluator. Output only valid JSON."},
                {"role": "user", "content": rendered},
            ],
            step_type=f"judge_{dimension}",
            prompt_hash=prompt_hash,
            run_id=run_id,
            session_id=session.session_id,
            turn_id="judge",
            response_schema=_JudgeOutput,
        )

        parsed = _JudgeOutput.model_validate_json(reply)
        score = max(1, min(5, parsed.score))

        write_judge_score(
            session_id=session.session_id,
            dimension=dimension,
            score=score,
            judge_model=self._llm.model_name,
            judge_prompt_hash=full_prompt_hash,
            rationale=parsed.rationale,
        )
        log.info(
            "judge scored session_id=%s dimension=%s score=%d",
            session.session_id, dimension, score,
        )


