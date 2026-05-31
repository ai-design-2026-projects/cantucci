import { useQuery } from '@tanstack/react-query'
import { getAllUmapPointsFetcher } from '@/api/services/snapshots'
import type { UmapPointDto } from '@/api/dto/snapshots'

/**
 * Fetch UMAP coordinates for all catalogued movies.
 * Used to render the uncoloured grey silhouette when no clustering is active.
 * Cached indefinitely — the data is stable after ingest.
 *
 * @returns TanStack Query result wrapping UmapPointDto[].
 */
export function useAllUmapPoints() {
    return useQuery<UmapPointDto[]>({
        queryKey: ['umap_points'],
        queryFn: getAllUmapPointsFetcher,
        staleTime: Infinity,
        retry: false,
    })
}
