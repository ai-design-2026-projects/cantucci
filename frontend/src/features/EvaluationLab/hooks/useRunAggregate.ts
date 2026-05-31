import { useQuery, useQueries } from '@tanstack/react-query'
import { getRunAggregateFetcher } from '@/api/services/eval'
import type { RunAggregateDto } from '@/api/dto/eval'

/**
 * Fetch the full aggregate for a single run (per-session metrics + judge scores + summary).
 * Polls every 5 s when the run is still running so the dashboard auto-updates.
 *
 * @param runId Run UUID string, or null/undefined when nothing is selected.
 * @param isRunning Whether the run is currently active (enables polling).
 * @returns TanStack Query result wrapping RunAggregateDto.
 */
export function useRunAggregate(
    runId: string | null | undefined,
    isRunning = false,
) {
    return useQuery<RunAggregateDto>({
        queryKey: ['eval', 'run', runId, 'aggregate'],
        queryFn: () => getRunAggregateFetcher(runId!),
        enabled: !!runId,
        staleTime: isRunning ? 0 : 30_000,
        refetchInterval: isRunning ? 5_000 : false,
    })
}

/**
 * Fetch aggregates for multiple runs in parallel (used by compare mode).
 *
 * @param runIds Array of run UUID strings.
 * @returns Array of TanStack Query results, one per run ID.
 */
export function useMultipleRunAggregates(runIds: string[]) {
    return useQueries({
        queries: runIds.map((id) => ({
            queryKey: ['eval', 'run', id, 'aggregate'],
            queryFn: () => getRunAggregateFetcher(id),
            staleTime: 30_000,
        })),
    })
}
