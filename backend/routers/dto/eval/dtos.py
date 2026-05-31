import uuid
from datetime import datetime

from pydantic import BaseModel


class RunDto(BaseModel):
    """Wire model for an eval run.

    Attributes:
        id:             Run UUID.
        name:           Optional human-readable label.
        condition:      Experimental condition (conversational | no_agents | monolithic | human).
        model_version:  Model tier string from config.
        config_hash:    SHA-256 8-char prefix of the YAML config used.
        seed:           Top-level RNG seed.
        status:         Run lifecycle status.
        notes:          Optional free-text notes.
        started_at:     Creation timestamp.
        ended_at:       Completion timestamp (None while active).
    """
    id: uuid.UUID
    name: str | None
    condition: str
    model_version: str | None
    config_hash: str
    seed: int
    status: str
    notes: str | None
    started_at: datetime
    ended_at: datetime | None


class PersonaDto(BaseModel):
    """Wire model for a persona.

    Attributes:
        id:         Persona UUID.
        slug:       Unique slug.
        verbosity:  Verbosity level (terse | medium | verbose).
        patience:   Patience float in [0, 1].
        created_at: Creation timestamp.
    """
    id: uuid.UUID
    slug: str
    verbosity: str
    patience: float
    created_at: datetime


class GroundTruthDto(BaseModel):
    """Wire model for a ground truth trajectory.

    Attributes:
        id:                 Ground truth UUID.
        slug:               Unique slug.
        version:            Schema version number.
        intent_description: Natural-language paraphrase of the trajectory intent.
        operations:         Ordered list of {op, concept} dicts.
        prompt_hash:        SHA-256 of the GT builder prompts.
        created_at:         Creation timestamp.
    """
    id: uuid.UUID
    slug: str
    version: int
    intent_description: str
    operations: list[dict]
    prompt_hash: str
    created_at: datetime


class TurnIntentDto(BaseModel):
    """Wire model for a single turn intent record.

    Attributes:
        id:               Row UUID.
        turn_number:      1-based turn ordinal.
        mode:             NavigationMode or DialogueMode value string.
        concept:          Semantic concept (may be None).
        confidence:       Classified confidence score.
        clarifier_fired:  True if the clarifier gate fired this turn.
        created_at:       Creation timestamp.
    """
    id: uuid.UUID
    turn_number: int
    mode: str
    concept: str | None
    confidence: float
    clarifier_fired: bool
    created_at: datetime


class ConversationMetricsDto(BaseModel):
    """Wire model for conversation-level deterministic metrics.

    Attributes:
        final_num_clusters:      Number of clusters at session end.
        operation_recall:        Fraction of GT ops matched, or None if no GT.
        clarifier_trigger_rate:  Rate of turns that triggered the clarifier.
        num_turns:               Total number of oracle turns.
        num_operations:          Total NavigationMode operations recorded.
        total_cost_usd:          Total LLM cost in USD.
        computed_at:             Metrics computation timestamp.
    """
    final_num_clusters: int
    operation_recall: float | None
    clarifier_trigger_rate: float | None
    num_turns: int
    num_operations: int
    total_cost_usd: float
    computed_at: datetime


class JudgeScoreDto(BaseModel):
    """Wire model for a single judge dimension score.

    Attributes:
        dimension:          Judge dimension name.
        score:              Score in [1, 5].
        judge_model:        Model identifier used for scoring.
        judge_prompt_hash:  SHA-256 of the rendered judge prompt.
        rationale:          One-sentence rationale from the judge.
        created_at:         Creation timestamp.
    """
    dimension: str
    score: int
    judge_model: str
    judge_prompt_hash: str
    rationale: str | None
    created_at: datetime


class EvalSessionDto(BaseModel):
    """Wire model for an eval session summary.

    Attributes:
        id:                   Session UUID.
        run_id:               Parent run UUID.
        conversation_id:      Conversation UUID.
        seed:                 Per-session RNG seed.
        condition:            Experimental condition.
        status:               Session lifecycle status.
        oracle_rating:        1–5 oracle self-rating (None for human).
        termination_rationale: Free-text oracle rationale.
        created_at:           Creation timestamp.
    """
    id: uuid.UUID
    run_id: uuid.UUID
    conversation_id: uuid.UUID
    seed: int
    condition: str
    status: str
    oracle_rating: int | None
    termination_rationale: str | None
    created_at: datetime


class EvalSessionDetailDto(EvalSessionDto):
    """Wire model for an eval session with full metrics and scores.

    Extends EvalSessionDto with per-session detail fields.

    Attributes:
        metrics:      Conversation-level metrics (None if not yet computed).
        judge_scores: All judge dimension scores for this session.
        turn_intents: Ordered per-turn intent records.
    """
    metrics: ConversationMetricsDto | None
    judge_scores: list[JudgeScoreDto]
    turn_intents: list[TurnIntentDto]


class SessionMetricsDto(BaseModel):
    """Metrics for one session within a run aggregate. All nullable for LEFT JOIN semantics.

    Attributes:
        final_num_clusters:     Number of clusters at session end, or None.
        operation_recall:       Fraction of GT ops matched, or None.
        clarifier_trigger_rate: Rate of turns that triggered the clarifier, or None.
        num_turns:              Total oracle turns.
        num_operations:         Total navigation operations.
        total_cost_usd:         Total LLM cost in USD.
        computed_at:            Metrics computation timestamp.
    """
    final_num_clusters: int | None
    operation_recall: float | None
    clarifier_trigger_rate: float | None
    num_turns: int
    num_operations: int
    total_cost_usd: float
    computed_at: datetime


class SessionAggregateRowDto(BaseModel):
    """One session's contribution to a run aggregate response.

    Attributes:
        eval_session_id:       Session UUID.
        conversation_id:       Linked conversation UUID.
        persona_id:            Oracle persona UUID, or None for human sessions.
        ground_truth_id:       Ground truth UUID, or None for human sessions.
        status:                Session lifecycle status.
        oracle_rating:         1–5 oracle self-rating, or None.
        termination_rationale: Free-text oracle rationale, or None.
        created_at:            Session creation timestamp.
        metrics:               Conversation-level metrics (None if not computed).
        judge_scores:          Latest judge score per dimension.
    """
    eval_session_id: uuid.UUID
    conversation_id: uuid.UUID
    persona_id: uuid.UUID | None
    ground_truth_id: uuid.UUID | None
    status: str
    oracle_rating: int | None
    termination_rationale: str | None
    created_at: datetime
    metrics: SessionMetricsDto | None
    judge_scores: list[JudgeScoreDto]


class RunAggregateSummaryDto(BaseModel):
    """Run-level summary block for KPI cards.

    Attributes:
        n_sessions:        Total number of sessions in the run.
        n_completed:       Sessions with a finished_* terminal status.
        mean_cost_usd:     Mean LLM cost across sessions with computed metrics, or None.
        mean_oracle_rating: Mean oracle self-rating across rated sessions, or None.
        mean_num_turns:    Mean turn count across sessions with computed metrics, or None.
    """
    n_sessions: int
    n_completed: int
    mean_cost_usd: float | None
    mean_oracle_rating: float | None
    mean_num_turns: float | None


class RunAggregateDto(BaseModel):
    """Full run aggregate response with per-session data and run-level summary.

    Attributes:
        run:             Parent run metadata.
        config_snapshot: Full YAML config dict stored for replay and display.
        sessions:        One entry per eval session, including metrics and judge scores.
        summary:         Convenience aggregate for KPI cards.
    """
    run: RunDto
    config_snapshot: dict
    sessions: list[SessionAggregateRowDto]
    summary: RunAggregateSummaryDto
