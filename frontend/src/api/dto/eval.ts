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
    id: string
    slug: string
    verbosity: string
    patience: number
    created_at: string
}

export interface GroundTruthDto {
    id: string
    slug: string
    version: number
    intent_description: string
    operations: Array<Record<string, string>>
    prompt_hash: string
    created_at: string
}

export interface TurnIntentDto {
    id: string
    turn_number: number
    mode: string
    concept: string | null
    confidence: number
    clarifier_fired: boolean
    created_at: string
}

export interface JudgeScoreDto {
    dimension: string
    score: number
    judge_model: string
    judge_prompt_hash: string
    rationale: string | null
    created_at: string
}

export interface ConversationMetricsDto {
    final_num_clusters: number
    clarifier_trigger_rate: number | null
    num_turns: number
    num_operations: number
    total_cost_usd: number
    computed_at: string
}

export interface EvalSessionDto {
    id: string
    run_id: string
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
}

export interface SessionMetricsDto {
    final_num_clusters: number | null
    clarifier_trigger_rate: number | null
    num_turns: number
    num_operations: number
    total_cost_usd: number
    computed_at: string
}

export interface SessionAggregateRowDto {
    eval_session_id: string
    conversation_id: string
    persona_id: string | null
    ground_truth_id: string | null
    status: string
    oracle_rating: number | null
    termination_rationale: string | null
    created_at: string
    metrics: SessionMetricsDto | null
    judge_scores: JudgeScoreDto[]
}

export interface RunAggregateSummaryDto {
    n_sessions: number
    n_completed: number
    mean_cost_usd: number | null
    mean_oracle_rating: number | null
    mean_num_turns: number | null
}

export interface RunAggregateDto {
    run: RunDto
    config_snapshot: Record<string, unknown>
    sessions: SessionAggregateRowDto[]
    summary: RunAggregateSummaryDto
}
