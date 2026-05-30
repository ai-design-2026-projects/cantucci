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
    return apiClient<RunDto[]>(`/eval/list_runs?limit=${limit}&offset=${offset}`)
}

/**
 * Fetch a run's full aggregate: per-session metrics, latest judge scores, and summary KPIs.
 *
 * @param runId Run UUID.
 * @returns RunAggregateDto.
 */
export async function getRunAggregateFetcher(runId: string): Promise<RunAggregateDto> {
    return apiClient<RunAggregateDto>(`/eval/get_run_aggregate/${runId}`)
}

/**
 * Fetch full detail for a single eval session (metrics + judge scores + turn intents).
 *
 * @param sessionId Eval session UUID.
 * @returns EvalSessionDetailDto.
 */
export async function getSessionDetailFetcher(sessionId: string): Promise<EvalSessionDetailDto> {
    return apiClient<EvalSessionDetailDto>(`/eval/get_session/${sessionId}`)
}

/**
 * List all evaluation personas.
 *
 * @returns Array of PersonaDto.
 */
export async function listPersonasFetcher(): Promise<PersonaDto[]> {
    return apiClient<PersonaDto[]>('/eval/list_personas')
}

/**
 * List all ground truth trajectories.
 *
 * @returns Array of GroundTruthDto.
 */
export async function listGroundTruthsFetcher(): Promise<GroundTruthDto[]> {
    return apiClient<GroundTruthDto[]>('/eval/list_ground_truths')
}
