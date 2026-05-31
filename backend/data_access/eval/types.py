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
        condition:       Experimental condition (conversational | monolithic | human).
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
        id:         Persona UUID.
        slug:       Unique identifier string for the persona.
        verbosity:  Reply-length dial (terse | medium | verbose).
        patience:   Willingness to continue after system misbehaviour [0, 1].
        definition: Extra JSONB definition fields.
        created_at: UTC creation timestamp.
    """
    id: uuid.UUID
    slug: str
    verbosity: str
    patience: float
    definition: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "PersonaRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            slug=r["slug"],
            verbosity=r["verbosity"],
            patience=r["patience"],
            definition=r["definition"] or {},
            created_at=r["created_at"],
        )


@dataclass(frozen=True, slots=True)
class GroundTruthRow:
    """A row from the ground_truths table.

    Attributes:
        id:                Ground truth UUID.
        slug:              Unique identifier string.
        version:           Schema version for replay compatibility.
        intent_description: Neutral intent description shown to the oracle.
        operations:        Ordered list of {op, concept} dicts (the oracle's private trajectory).
        seed_movie_ids:    TMDB IDs of movies that seeded GT generation (audit only), or None.
        prompt_hash:       SHA-256 of the GT builder prompts used at creation.
        created_at:        UTC creation timestamp.
    """
    id: uuid.UUID
    slug: str
    version: int
    intent_description: str
    operations: list[dict[str, str]]
    seed_movie_ids: list[int] | None
    prompt_hash: str
    created_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "GroundTruthRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            slug=r["slug"],
            version=r["version"],
            intent_description=r["intent_description"],
            operations=list(r["operations"]) if r["operations"] else [],
            seed_movie_ids=list(r["seed_movie_ids"]) if r["seed_movie_ids"] else None,
            prompt_hash=r["prompt_hash"],
            created_at=r["created_at"],
        )


@dataclass(frozen=True, slots=True)
class EvalSessionRow:
    """A row from the eval_sessions table.

    Links a conversation to an eval run, persona, and ground truth.
    persona_id and ground_truth_id are None for human-oracle sessions.

    Attributes:
        id:                    Eval session UUID.
        run_id:                Parent run UUID.
        conversation_id:       Linked conversation UUID.
        persona_id:            Oracle persona UUID, or None for human.
        ground_truth_id:       Ground truth UUID, or None for human.
        seed:                  Per-session RNG seed.
        condition:             Experimental condition (conversational | monolithic | human).
        status:                Session lifecycle (active | finished_trajectory | finished_misbehaviour | finished_budget).
        termination_rationale: Free-text rationale from oracle on stop, or None.
        oracle_rating:         1–5 self-rating from oracle at session end, or None for human.
        created_at:            UTC creation timestamp.
    """
    id: uuid.UUID
    run_id: uuid.UUID
    conversation_id: uuid.UUID
    persona_id: uuid.UUID | None
    ground_truth_id: uuid.UUID | None
    seed: int
    condition: str
    status: str
    termination_rationale: str | None
    oracle_rating: int | None
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
            condition=r["condition"],
            status=r["status"],
            termination_rationale=r["termination_rationale"],
            oracle_rating=r["oracle_rating"],
            created_at=r["created_at"],
        )


@dataclass(frozen=True, slots=True)
class TurnIntentRow:
    """A row from the turn_intents table.

    Persists the structured coordinator intent trace for each turn. Multiple rows
    per (conversation_id, turn_number) are allowed for compound turns.

    Attributes:
        id:               Turn intent UUID.
        conversation_id:  Parent conversation UUID.
        turn_number:      1-based oracle turn ordinal.
        mode:             NavigationMode or DialogueMode value string.
        concept:          Semantic concept string, or None.
        target_cluster_id: Target cluster UUID, or None.
        confidence:       Intent confidence in [0, 1].
        clarifier_fired:  True if the clarifier gate fired this turn.
        raw_intent:       Full raw intent JSON for audit.
        created_at:       UTC creation timestamp.
    """
    id: uuid.UUID
    conversation_id: uuid.UUID
    turn_number: int
    mode: str
    concept: str | None
    target_cluster_id: uuid.UUID | None
    confidence: float
    clarifier_fired: bool
    raw_intent: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "TurnIntentRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            id=r["id"],
            conversation_id=r["conversation_id"],
            turn_number=r["turn_number"],
            mode=r["mode"],
            concept=r["concept"],
            target_cluster_id=r["target_cluster_id"],
            confidence=r["confidence"],
            clarifier_fired=r["clarifier_fired"],
            raw_intent=r["raw_intent"] or {},
            created_at=r["created_at"],
        )


@dataclass(frozen=True, slots=True)
class ConversationMetricsRow:
    """A row from the conversation_metrics table.

    All deterministic eval metrics for one conversation; computed post-hoc and
    rewritable on recompute (PK = conversation_id).

    Attributes:
        conversation_id:       Parent conversation UUID.
        final_num_clusters:    Number of clusters in the final snapshot.
        operation_recall:      Fraction of GT operations executed, or None for human sessions.
        clarifier_trigger_rate: Fraction of turns on which the clarifier gate fired.
        num_turns:             Total oracle turns in the conversation.
        num_operations:        Total navigation operations executed.
        total_cost_usd:        Accumulated LLM cost for the conversation.
        computed_at:           UTC timestamp of this computation.
    """
    conversation_id: uuid.UUID
    final_num_clusters: int | None
    operation_recall: float | None
    clarifier_trigger_rate: float | None
    num_turns: int
    num_operations: int
    total_cost_usd: float
    computed_at: datetime

    @classmethod
    def from_row(cls, r: dict) -> "ConversationMetricsRow":
        """Construct from a psycopg dict_row result."""
        return cls(
            conversation_id=r["conversation_id"],
            final_num_clusters=r["final_num_clusters"],
            operation_recall=r["operation_recall"],
            clarifier_trigger_rate=r["clarifier_trigger_rate"],
            num_turns=r["num_turns"],
            num_operations=r["num_operations"],
            total_cost_usd=float(r["total_cost_usd"]),
            computed_at=r["computed_at"],
        )


@dataclass(frozen=True, slots=True)
class JudgeScoreRow:
    """A row from the judge_scores table.

    Append-only; multiple judge versions can coexist per (conversation, dimension).

    Attributes:
        id:                Judge score UUID.
        conversation_id:   Scored conversation UUID.
        dimension:         Judge dimension name.
        score:             Integer score in [1, 5].
        rationale:         One-sentence rationale from the judge.
        judge_model:       Model identifier string.
        judge_prompt_hash: SHA-256 hex of the rendered judge prompt.
        created_at:        UTC creation timestamp.
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

    @classmethod
    def from_jsonb(cls, js: dict, conversation_id: uuid.UUID) -> "JudgeScoreRow":
        """Construct from a JSONB-aggregated dict (UUIDs and datetimes are strings).

        Args:
            js:              Dict produced by jsonb_build_object in an aggregate query.
            conversation_id: Parent conversation UUID (not embedded in the JSON dict).

        Returns:
            JudgeScoreRow with Python-native types.
        """
        return cls(
            id=uuid.UUID(js["id"]),
            conversation_id=conversation_id,
            dimension=js["dimension"],
            score=js["score"],
            rationale=js.get("rationale"),
            judge_model=js["judge_model"],
            judge_prompt_hash=js["judge_prompt_hash"],
            created_at=datetime.fromisoformat(js["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class RunAggregateSessionRow:
    """Composite of eval_session + conversation_metrics + judge_scores for one session.

    Returned by get_run_aggregate; all metric fields are None if not yet computed.

    Attributes:
        id:                    Eval session UUID.
        run_id:                Parent run UUID.
        conversation_id:       Linked conversation UUID.
        persona_id:            Oracle persona UUID, or None for human.
        ground_truth_id:       Ground truth UUID, or None for human.
        seed:                  Per-session RNG seed.
        condition:             Experimental condition.
        status:                Session lifecycle status.
        termination_rationale: Free-text oracle rationale, or None.
        oracle_rating:         1–5 oracle self-rating, or None.
        created_at:            UTC creation timestamp.
        final_num_clusters:    Final cluster count, or None.
        operation_recall:      Operation recall vs ground truth, or None.
        clarifier_trigger_rate: Clarifier trigger rate, or None.
        num_turns:             Total turns (None means metrics not computed).
        num_operations:        Total operations (None means metrics not computed).
        total_cost_usd:        Total LLM cost (None means metrics not computed).
        metrics_computed_at:   Metrics computation timestamp, or None.
        judge_scores:          Latest judge score per dimension (may be empty).
    """
    id: uuid.UUID
    run_id: uuid.UUID
    conversation_id: uuid.UUID
    persona_id: uuid.UUID | None
    ground_truth_id: uuid.UUID | None
    seed: int
    condition: str
    status: str
    termination_rationale: str | None
    oracle_rating: int | None
    created_at: datetime
    final_num_clusters: int | None
    operation_recall: float | None
    clarifier_trigger_rate: float | None
    num_turns: int | None
    num_operations: int | None
    total_cost_usd: float | None
    metrics_computed_at: datetime | None
    judge_scores: list[JudgeScoreRow]

    @classmethod
    def from_row(cls, r: dict) -> "RunAggregateSessionRow":
        """Construct from a psycopg dict_row result of the aggregate query."""
        conversation_id: uuid.UUID = r["conversation_id"]
        judge_scores = [
            JudgeScoreRow.from_jsonb(js, conversation_id)
            for js in (r["judge_scores"] or [])
        ]
        return cls(
            id=r["id"],
            run_id=r["run_id"],
            conversation_id=conversation_id,
            persona_id=r["persona_id"],
            ground_truth_id=r["ground_truth_id"],
            seed=r["seed"],
            condition=r["condition"],
            status=r["status"],
            termination_rationale=r["termination_rationale"],
            oracle_rating=r["oracle_rating"],
            created_at=r["created_at"],
            final_num_clusters=r["final_num_clusters"],
            operation_recall=r["operation_recall"],
            clarifier_trigger_rate=r["clarifier_trigger_rate"],
            num_turns=r["num_turns"],
            num_operations=r["num_operations"],
            total_cost_usd=float(r["total_cost_usd"]) if r["total_cost_usd"] is not None else None,
            metrics_computed_at=r["metrics_computed_at"],
            judge_scores=judge_scores,
        )
