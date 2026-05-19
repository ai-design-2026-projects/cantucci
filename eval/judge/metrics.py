"""
Objective eval metrics computed against a ground-truth film set.
All metrics operate on integer TMDB movie IDs.  The recommended list is
assumed to be in descending relevance order (highest-score film first), as
returned by ``RecommendationDto.films``.
"""

import math
import logging

from backend.routers.dtos import TurnDto

log = logging.getLogger(__name__)


def precision_at_k(recommended_ids: list[int], gt_ids: list[int], k: int) -> float:
    """
    Fraction of the top-K recommendations that appear in the ground-truth set.
    Args:
        recommended_ids: Ordered list of recommended TMDB IDs (descending score).
        gt_ids:          Ground-truth TMDB IDs (order-insensitive).
        k:               Rank cutoff.
    Returns:
        Precision@K in ``[0.0, 1.0]``
    """
    if k == 0:
        return 0.0
    gt_set = set(gt_ids)
    top_k = recommended_ids[:k]
    hits = sum(1 for m in top_k if m in gt_set)
    return hits / k


def recall_at_k(recommended_ids: list[int], gt_ids: list[int], k: int) -> float:
    """
    Fraction of the ground-truth set recovered in the top-K recommendations.
    Args:
        recommended_ids: Ordered list of recommended TMDB IDs (descending score).
        gt_ids:          Ground-truth TMDB IDs (order-insensitive).
        k:               Rank cutoff.
    Returns:
        Recall@K in ``[0.0, 1.0]``
    """
    if not gt_ids or k == 0:
        return 0.0
    gt_set = set(gt_ids)
    top_k = recommended_ids[:k]
    hits = sum(1 for m in top_k if m in gt_set)
    return hits / len(gt_ids)


def ndcg_at_k(recommended_ids: list[int], gt_ids: list[int], k: int) -> float:
    """
    Normalised Discounted Cumulative Gain at rank K.
    Relevance is binary: 1 if the film is in the ground-truth set, 0 otherwise.
    The gain is discounted logarithmically by rank to emphasise higher-ranked hits.
    Args:
        recommended_ids: Ordered list of recommended TMDB IDs (descending score).
        gt_ids:          Ground-truth TMDB IDs (order-insensitive).
        k:               Rank cutoff.
    Returns:
        NDCG@K in ``[0.0, 1.0]``
    """
    if not gt_ids or k == 0:
        return 0.0
    gt_set = set(gt_ids)
    top_k = recommended_ids[:k]

    dcg = sum(
        1.0 / math.log2(rank + 2)
        for rank, mid in enumerate(top_k)
        if mid in gt_set
    )
    n_relevant = min(len(gt_ids), k)
    idcg = sum(1.0 / math.log2(rank + 2) for rank in range(n_relevant))

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def cognitive_load(turn: TurnDto) -> float:
    """
    Estimate cognitive load for a single turn.
    Approximates the information density the oracle must process:
    number of clusters shown (from mid-stream snapshot, not available here),
    recommendation size, and question length.  Produces a value roughly in
    ``[0.0, 5.0]``.

    Args:
        turn: Completed turn DTO.

    Returns:
        Non-negative float representing relative cognitive load.
    """
    film_load = len(turn.recommendation.films) * 0.3 if turn.recommendation else 0.0
    question_words = len(turn.assistant_message.split())
    question_load = min(question_words / 40.0, 2.0)
    return round(film_load + question_load, 3)
