import { useQuery } from '@tanstack/react-query'
import { listRunsFetcher } from '@/api/services/eval'
import type { RunDto } from '@/api/dto/eval'

/**
 * Fetch all eval runs (up to 200), newest first.
 * Polls every 5 s so a run that is currently in progress auto-updates.
 *
 * @returns TanStack Query result wrapping RunDto[].
 */
export function useRuns() {
    return useQuery<RunDto[]>({
        queryKey: ['eval', 'runs'],
        queryFn: () => listRunsFetcher(200, 0),
        staleTime: 5_000,
        refetchInterval: 5_000,
    })
}
