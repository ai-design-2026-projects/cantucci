import { apiClient } from '../client'
import type {
    EvalSessionDetailDto,
    GroundTruthDto,
    PersonaDto,
    RunAggregateDto,
    RunDto,
} from '../dto/eval'

/**
 * List eval runs, newest first.
 *
 * @param limit  Maximum number of runs (default 50).
 * @param offset Pagination offset (default 0).
 * @returns Array of RunDto.
 */
export async function listRunsFetcher(limit = 50, offset = 0): Promise<RunDto[]> {
    return apiClient<RunDto[]>(`/eval/runs?limit=${limit}&offset=${offset}`)
}

/**
 * Fetch a run's full aggregate: per-session metrics, latest judge scores, and summary KPIs.
 *
 * @param runId Run UUID.
 * @returns RunAggregateDto.
 */
export async function getRunAggregateFetcher(runId: string): Promise<RunAggregateDto> {
    return apiClient<RunAggregateDto>(`/eval/runs/${runId}/aggregate`)
}

/**
 * Fetch full detail for a single eval session (metrics + judge scores + turn intents).
 *
 * @param sessionId Eval session UUID.
 * @returns EvalSessionDetailDto.
 */
export async function getSessionDetailFetcher(sessionId: string): Promise<EvalSessionDetailDto> {
    return apiClient<EvalSessionDetailDto>(`/eval/sessions/${sessionId}`)
}

/**
 * List all evaluation personas.
 *
 * @returns Array of PersonaDto.
 */
export async function listPersonasFetcher(): Promise<PersonaDto[]> {
    return apiClient<PersonaDto[]>('/eval/personas')
}

/**
 * List all ground truth trajectories.
 *
 * @returns Array of GroundTruthDto.
 */
export async function listGroundTruthsFetcher(): Promise<GroundTruthDto[]> {
    return apiClient<GroundTruthDto[]>('/eval/ground-truths')
}
