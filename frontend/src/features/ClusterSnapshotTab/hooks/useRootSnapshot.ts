import { useQuery } from '@tanstack/react-query'
import { getRootSnapshotFetcher } from '@/api/services/snapshots'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'

/**
 * Fetch hook for the root (base HDBSCAN) cluster snapshot.
 * Used to populate the scatter plot silhouette when no conversation is active.
 *
 * @returns TanStack Query result wrapping ClusterSnapshotDto, or undefined if not yet ingested.
 */
export function useRootSnapshot() {
	return useQuery<ClusterSnapshotDto>({
		queryKey: ['snapshot', 'root'],
		queryFn: getRootSnapshotFetcher,
		staleTime: Infinity,
		retry: false,
	})
}
