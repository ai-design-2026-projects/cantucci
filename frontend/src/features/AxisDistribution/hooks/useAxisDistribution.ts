import { useQuery } from '@tanstack/react-query'

import { getAxisDistributionFetcher } from '@/api/services/concepts'
import type { AxisDistributionDto } from '@/api/dto/concepts'

export function useAxisDistribution(conceptId: string | null | undefined, enabled: boolean) {
    return useQuery<AxisDistributionDto>({
        queryKey: ['axis', conceptId],
        queryFn: () => getAxisDistributionFetcher(conceptId!),
        enabled: !!conceptId && enabled,
        staleTime: 60_000,
    })
}
