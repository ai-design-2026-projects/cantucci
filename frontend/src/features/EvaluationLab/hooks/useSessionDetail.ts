import { useQuery } from '@tanstack/react-query'
import { getSessionDetailFetcher } from '@/api/services/eval'
import type { EvalSessionDetailDto } from '@/api/dto/eval'

/**
 * Fetch full detail for one eval session (metrics + judge scores + turn intents).
 *
 * @param sessionId Eval session UUID, or null/undefined when nothing is selected.
 * @returns TanStack Query result wrapping EvalSessionDetailDto.
 */
export function useSessionDetail(sessionId: string | null | undefined) {
    return useQuery<EvalSessionDetailDto>({
        queryKey: ['eval', 'session', sessionId],
        queryFn: () => getSessionDetailFetcher(sessionId!),
        enabled: !!sessionId,
        staleTime: 30_000,
    })
}
