from backend.data_access.eval.types import (
    ConversationMetricsRow,
    EvalSessionRow,
    GroundTruthRow,
    JudgeScoreRow,
    PersonaRow,
    RunAggregateSessionRow,
    RunRow,
    TurnIntentRow,
)
from backend.routers.dto.eval.dtos import (
    ConversationMetricsDto,
    EvalSessionDetailDto,
    EvalSessionDto,
    GroundTruthDto,
    JudgeScoreDto,
    PersonaDto,
    RunAggregateDto,
    RunAggregateSummaryDto,
    RunDto,
    SessionAggregateRowDto,
    SessionMetricsDto,
    TurnIntentDto,
)


def run_to_dto(row: RunRow) -> RunDto:
    """Convert a RunRow to a RunDto.

    Args:
        row: Data-access layer run row.

    Returns:
        Wire-safe RunDto.
    """
    return RunDto(
        id=row.run_id,
        name=row.name,
        condition=row.condition,
        model_version=row.model_version,
        config_hash=row.config_hash,
        seed=row.seed,
        status=row.status,
        notes=row.notes,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


def persona_to_dto(row: PersonaRow) -> PersonaDto:
    """Convert a PersonaRow to a PersonaDto.

    Args:
        row: Data-access layer persona row.

    Returns:
        Wire-safe PersonaDto.
    """
    return PersonaDto(
        id=row.id,
        slug=row.slug,
        verbosity=row.verbosity,
        patience=row.patience,
        created_at=row.created_at,
    )


def ground_truth_to_dto(row: GroundTruthRow) -> GroundTruthDto:
    """Convert a GroundTruthRow to a GroundTruthDto.

    Args:
        row: Data-access layer ground truth row.

    Returns:
        Wire-safe GroundTruthDto.
    """
    return GroundTruthDto(
        id=row.id,
        slug=row.slug,
        version=row.version,
        intent_description=row.intent_description,
        operations=row.operations,
        prompt_hash=row.prompt_hash,
        created_at=row.created_at,
    )


def turn_intent_to_dto(row: TurnIntentRow) -> TurnIntentDto:
    """Convert a TurnIntentRow to a TurnIntentDto.

    Args:
        row: Data-access layer turn intent row.

    Returns:
        Wire-safe TurnIntentDto.
    """
    return TurnIntentDto(
        id=row.id,
        turn_number=row.turn_number,
        mode=row.mode,
        concept=row.concept,
        confidence=row.confidence,
        clarifier_fired=row.clarifier_fired,
        created_at=row.created_at,
    )


def metrics_to_dto(row: ConversationMetricsRow) -> ConversationMetricsDto:
    """Convert a ConversationMetricsRow to a ConversationMetricsDto.

    Args:
        row: Data-access layer metrics row.

    Returns:
        Wire-safe ConversationMetricsDto.
    """
    return ConversationMetricsDto(
        final_num_clusters=row.final_num_clusters,
        operation_recall=row.operation_recall,
        clarifier_trigger_rate=row.clarifier_trigger_rate,
        num_turns=row.num_turns,
        num_operations=row.num_operations,
        total_cost_usd=float(row.total_cost_usd),
        computed_at=row.computed_at,
    )


def judge_score_to_dto(row: JudgeScoreRow) -> JudgeScoreDto:
    """Convert a JudgeScoreRow to a JudgeScoreDto.

    Args:
        row: Data-access layer judge score row.

    Returns:
        Wire-safe JudgeScoreDto.
    """
    return JudgeScoreDto(
        dimension=row.dimension,
        score=row.score,
        judge_model=row.judge_model,
        judge_prompt_hash=row.judge_prompt_hash,
        rationale=row.rationale,
        created_at=row.created_at,
    )


def eval_session_to_dto(row: EvalSessionRow) -> EvalSessionDto:
    """Convert an EvalSessionRow to an EvalSessionDto.

    Args:
        row: Data-access layer eval session row.

    Returns:
        Wire-safe EvalSessionDto.
    """
    return EvalSessionDto(
        id=row.id,
        run_id=row.run_id,
        conversation_id=row.conversation_id,
        seed=row.seed,
        condition=row.condition,
        status=row.status,
        oracle_rating=row.oracle_rating,
        termination_rationale=row.termination_rationale,
        created_at=row.created_at,
    )


def build_session_aggregate_row_dto(row: RunAggregateSessionRow) -> SessionAggregateRowDto:
    """Convert a RunAggregateSessionRow to a SessionAggregateRowDto.

    Args:
        row: Composite session row from the aggregate query.

    Returns:
        Wire-safe SessionAggregateRowDto with nested metrics and judge scores.
    """
    metrics: SessionMetricsDto | None = None
    if row.num_turns is not None:
        metrics = SessionMetricsDto(
            final_num_clusters=row.final_num_clusters,
            operation_recall=row.operation_recall,
            clarifier_trigger_rate=row.clarifier_trigger_rate,
            num_turns=row.num_turns,
            num_operations=row.num_operations or 0,
            total_cost_usd=row.total_cost_usd or 0.0,
            computed_at=row.metrics_computed_at,
        )
    return SessionAggregateRowDto(
        eval_session_id=row.id,
        conversation_id=row.conversation_id,
        persona_id=row.persona_id,
        ground_truth_id=row.ground_truth_id,
        status=row.status,
        oracle_rating=row.oracle_rating,
        termination_rationale=row.termination_rationale,
        created_at=row.created_at,
        metrics=metrics,
        judge_scores=[judge_score_to_dto(js) for js in row.judge_scores],
    )


def build_run_aggregate_dto(run: RunRow, sessions: list[RunAggregateSessionRow]) -> RunAggregateDto:
    """Build a RunAggregateDto from a run row and its session aggregate rows.

    Computes summary statistics from the session list.

    Args:
        run:      The parent run row.
        sessions: All sessions for the run, each with metrics and judge scores.

    Returns:
        Wire-safe RunAggregateDto with sessions and run-level summary.
    """
    session_dtos = [build_session_aggregate_row_dto(s) for s in sessions]

    completed = [s for s in sessions if s.status.startswith("finished_")]
    costs = [s.total_cost_usd for s in sessions if s.total_cost_usd is not None]
    ratings = [s.oracle_rating for s in sessions if s.oracle_rating is not None]
    turns = [s.num_turns for s in sessions if s.num_turns is not None]

    summary = RunAggregateSummaryDto(
        n_sessions=len(sessions),
        n_completed=len(completed),
        mean_cost_usd=sum(costs) / len(costs) if costs else None,
        mean_oracle_rating=sum(ratings) / len(ratings) if ratings else None,
        mean_num_turns=sum(turns) / len(turns) if turns else None,
    )

    return RunAggregateDto(
        run=run_to_dto(run),
        config_snapshot=run.config_snapshot,
        sessions=session_dtos,
        summary=summary,
    )


def eval_session_to_detail_dto(
    row: EvalSessionRow,
    metrics: ConversationMetricsRow | None,
    judge_scores: list[JudgeScoreRow],
    turn_intents: list[TurnIntentRow],
    persona: PersonaRow | None,
) -> EvalSessionDetailDto:
    """Convert an EvalSessionRow and associated data to an EvalSessionDetailDto.

    Args:
        row:          Data-access layer eval session row.
        metrics:      Conversation metrics row (may be None if not yet computed).
        judge_scores: All judge score rows for this session's conversation.
        turn_intents: All turn intent rows for this session's conversation.
        persona:      Persona row for this session (None when persona_id is unset).

    Returns:
        Wire-safe EvalSessionDetailDto with nested metrics, scores, intents, and persona.
    """
    return EvalSessionDetailDto(
        id=row.id,
        run_id=row.run_id,
        conversation_id=row.conversation_id,
        seed=row.seed,
        condition=row.condition,
        status=row.status,
        oracle_rating=row.oracle_rating,
        termination_rationale=row.termination_rationale,
        created_at=row.created_at,
        metrics=metrics_to_dto(metrics) if metrics else None,
        judge_scores=[judge_score_to_dto(s) for s in judge_scores],
        turn_intents=sorted(
            [turn_intent_to_dto(t) for t in turn_intents],
            key=lambda t: (t.turn_number, t.mode),
        ),
        persona=persona_to_dto(persona) if persona else None,
    )
