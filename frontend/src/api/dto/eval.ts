export interface RunDto {
    id: string
    name: string | null
    condition: string
    model_version: string | null
    config_hash: string
    seed: number
    status: string
    notes: string | null
    started_at: string
    ended_at: string | null
}

export interface PersonaDto {
    slug: string
    verbosity: string
    patience: number
}

export interface GroundTruthDto {
    slug: string
    intent_description: string
    operations: Array<Record<string, string>>
}

export interface TurnIntentDto {
    id: string
    turn_number: number
    mode: string
    concept: string | null
    confidence: number
    clarifier_fired: boolean
}

export interface JudgeScoreDto {
    dimension: string
    score: number
    rationale: string | null
}

export interface ConversationMetricsDto {
    final_num_clusters: number
    clarifier_trigger_rate: number | null
    num_turns: number
    num_operations: number
    total_cost_usd: number
}

export interface EvalSessionDto {
    id: string
    conversation_id: string
    seed: number
    condition: string
    status: string
    oracle_rating: number | null
    termination_rationale: string | null
    created_at: string
}

export interface EvalSessionDetailDto extends EvalSessionDto {
    metrics: ConversationMetricsDto | null
    judge_scores: JudgeScoreDto[]
    turn_intents: TurnIntentDto[]
    persona: PersonaDto | null
    ground_truth: GroundTruthDto | null
}

export interface SessionMetricsDto {
    final_num_clusters: number | null
    clarifier_trigger_rate: number | null
    num_turns: number
    num_operations: number
    total_cost_usd: number
}

export interface SessionAggregateRowDto {
    eval_session_id: string
    status: string
    oracle_rating: number | null
    created_at: string
    metrics: SessionMetricsDto | null
    judge_scores: JudgeScoreDto[]
    persona_slug: string | null
    persona_verbosity: string | null
    persona_patience: number | null
    mean_confidence: number | null
    ground_truth_slug: string | null
}

export interface RunAggregateSummaryDto {
    n_sessions: number
    n_completed: number
}

export interface RunAggregateDto {
    run: RunDto
    config_snapshot: Record<string, unknown>
    sessions: SessionAggregateRowDto[]
    summary: RunAggregateSummaryDto
}
