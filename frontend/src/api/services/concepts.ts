import { apiClient } from '@/api/client'
import type { AxisDistributionDto } from '@/api/dto/concepts'

/**
 * Fetch the distribution of movies along a concept's linear axis.
 * Scores are normalised to [-1, 1]; pole labels are included in the response.
 *
 * @param conceptId - Concept UUID.
 * @returns AxisDistributionDto with per-movie scores and pole labels.
 */
export async function getAxisDistributionFetcher(conceptId: string): Promise<AxisDistributionDto> {
    return apiClient<AxisDistributionDto>(`/concepts/get_axis/${conceptId}`)
}
