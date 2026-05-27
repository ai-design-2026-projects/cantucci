import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RunRow:
    """A row from the runs table.

    Attributes:
        run_id:          Experiment run UUID.
        config_hash:     SHA-256 8-char prefix of the active YAML config.
        config_snapshot: Full YAML config dict stored for replay.
        seed:            RNG seed for the run.
        started_at:      UTC start timestamp.
        name:            Human-readable run label.
        condition:       Experimental condition (conversational | baseline | human).
        model_version:   LLM model identifier string.
        ended_at:        UTC end timestamp, or None if still running.
        status:          Run lifecycle status (running | completed | aborted).
        notes:           Free-text notes.
    """
    run_id: uuid.UUID
    config_hash: str
    config_snapshot: dict[str, Any]
    seed: int
    started_at: datetime
    name: str | None
    condition: str | None
    model_version: str | None
    ended_at: datetime | None
    status: str
    notes: str | None

    @classmethod
    def from_row(cls, r: dict) -> "RunRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            run_id=r["run_id"],
            config_hash=r["config_hash"],
            config_snapshot=r["config_snapshot"],
            seed=r["seed"],
            started_at=r["started_at"],
            name=r["name"],
            condition=r["condition"],
            model_version=r["model_version"],
            ended_at=r["ended_at"],
            status=r["status"],
            notes=r["notes"],
        )


@dataclass(frozen=True, slots=True)
class PersonaRow:
    """A row from the personas table.

    Attributes:
        id:                Persona UUID.
        slug:              Unique identifier string for the persona.
        verbosity:         Reply-length dial (terse | medium | verbose).
        decisiveness:      Minimum-turn acceptance probability dial [0, 1].
        drift_probability: Per-turn tangent injection probability [0, 1].
        contradiction_rate: Per-turn self-contradiction injection probability [0, 1].
        definition:        Extra JSONB definition fields.
        created_at:        UTC creation timestamp.
    """
    id: uuid.UUID
    slug: str
    verbosity: str
    decisiveness: float
    drift_probability: float
    contradiction_rate: float
    definition: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "PersonaRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            slug=r["slug"],
            verbosity=r["verbosity"],
            decisiveness=r["decisiveness"],
            drift_probability=r["drift_probability"],
            contradiction_rate=r["contradiction_rate"],
            definition=r["definition"] or {},
            created_at=r["created_at"],
        )


@dataclass(frozen=True, slots=True)
class GroundTruthRow:
    """A row from the ground_truths table.

    Attributes:
        id:               Ground truth UUID.
        slug:             Unique identifier string.
        description:      Neutral taste description shown to the oracle.
        seed_movie_ids:   Seed TMDB IDs used to expand the target set.
        target_movie_ids: Hidden expanded film set used for spec-satisfaction scoring.
        spec:             Positive/negative criteria dict for hidden-spec evaluation.
        created_at:       UTC creation timestamp.
    """
    id: uuid.UUID
    slug: str
    description: str
    seed_movie_ids: list[int]
    target_movie_ids: list[int]
    spec: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "GroundTruthRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            slug=r["slug"],
            description=r["description"],
            seed_movie_ids=list(r["seed_movie_ids"]) if r["seed_movie_ids"] else [],
            target_movie_ids=list(r["target_movie_ids"]) if r["target_movie_ids"] else [],
            spec=r["spec"] or {},
            created_at=r["created_at"],
        )


@dataclass(frozen=True, slots=True)
class EvalSessionRow:
    """A row from the eval_sessions table.

    Links a conversation to an eval run, persona, and ground truth.
    persona_id and ground_truth_id are None for human-oracle sessions.

    Attributes:
        id:               Eval session UUID.
        run_id:           Parent run UUID.
        conversation_id:  Linked conversation UUID.
        persona_id:       Oracle persona UUID, or None for human.
        ground_truth_id:  Ground truth UUID, or None for human.
        seed:             Per-session RNG seed.
        status:           Session lifecycle status (active | converged | abandoned).
        created_at:       UTC creation timestamp.
    """
    id: uuid.UUID
    run_id: uuid.UUID
    conversation_id: uuid.UUID
    persona_id: uuid.UUID | None
    ground_truth_id: uuid.UUID | None
    seed: int
    status: str
    created_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "EvalSessionRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            run_id=r["run_id"],
            conversation_id=r["conversation_id"],
            persona_id=r["persona_id"],
            ground_truth_id=r["ground_truth_id"],
            seed=r["seed"],
            status=r["status"],
            created_at=r["created_at"],
        )


@dataclass(frozen=True, slots=True)
class ConversationMetricsRow:
    """A row from the conversation_metrics table.

    All deterministic eval metrics for one conversation; computed post-hoc and
    rewritable on recompute (PK = conversation_id).

    Attributes:
        conversation_id:       Parent conversation UUID.
        silhouette:            Silhouette score of the final clustering, or None.
        mean_membership_prob:  Mean argmax membership probability across all movies.
        noise_fraction:        Fraction of movies with low membership probability.
        final_num_clusters:    Number of clusters in the final snapshot.
        spec_satisfaction_rate: Fraction of final-cluster members satisfying the spec, or None.
        converged:             True if the oracle explicitly accepted (always False for human sessions).
        turns_to_convergence:  Oracle turn on which acceptance fired, or None.
        num_turns:             Total oracle turns in the conversation.
        total_cost_usd:        Accumulated LLM cost for the conversation.
        computed_at:           UTC timestamp of this computation.
    """
    conversation_id: uuid.UUID
    silhouette: float | None
    mean_membership_prob: float | None
    noise_fraction: float | None
    final_num_clusters: int | None
    spec_satisfaction_rate: float | None
    converged: bool
    turns_to_convergence: int | None
    num_turns: int
    total_cost_usd: float
    computed_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "ConversationMetricsRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            conversation_id=r["conversation_id"],
            silhouette=r["silhouette"],
            mean_membership_prob=r["mean_membership_prob"],
            noise_fraction=r["noise_fraction"],
            final_num_clusters=r["final_num_clusters"],
            spec_satisfaction_rate=r["spec_satisfaction_rate"],
            converged=r["converged"],
            turns_to_convergence=r["turns_to_convergence"],
            num_turns=r["num_turns"],
            total_cost_usd=float(r["total_cost_usd"]),
            computed_at=r["computed_at"],
        )


@dataclass(frozen=True, slots=True)
class JudgeScoreRow:
    """A row from the judge_scores table.

    Append-only; multiple judge versions can coexist per (conversation, dimension).

    Attributes:
        id:               Judge score UUID.
        conversation_id:  Scored conversation UUID.
        dimension:        Judge dimension name.
        score:            Integer score in [1, 5].
        rationale:        One-sentence rationale from the judge.
        judge_model:      Model identifier string.
        judge_prompt_hash: SHA-256 hex of the rendered judge prompt.
        created_at:       UTC creation timestamp.
    """
    id: uuid.UUID
    conversation_id: uuid.UUID
    dimension: str
    score: int
    rationale: str | None
    judge_model: str
    judge_prompt_hash: str
    created_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "JudgeScoreRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            conversation_id=r["conversation_id"],
            dimension=r["dimension"],
            score=r["score"],
            rationale=r["rationale"],
            judge_model=r["judge_model"],
            judge_prompt_hash=r["judge_prompt_hash"],
            created_at=r["created_at"],
        )
