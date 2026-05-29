import { apiClient } from '@/api/client'
import type { AxisDistributionDto } from '@/api/dto/concepts'

export async function getAxisDistributionFetcher(conceptId: string): Promise<AxisDistributionDto> {
    return apiClient<AxisDistributionDto>(`/concepts/${conceptId}/axis`)
}
