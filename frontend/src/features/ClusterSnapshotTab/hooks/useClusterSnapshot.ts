import { useQuery } from '@tanstack/react-query'
import { getSnapshotFetcher } from '@/api/services/snapshots'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'

/**
 * Fetch hook for loading a cluster snapshot with its full cluster list.
 *
 * @param snapshotId - Cluster snapshot UUID, or undefined when none is active.
 * @returns TanStack Query result wrapping ClusterSnapshotDto.
 */
export function useClusterSnapshot(snapshotId: string | null | undefined) {
	return useQuery<ClusterSnapshotDto>({
		queryKey: ['snapshot', snapshotId],
		queryFn: () => getSnapshotFetcher(snapshotId!),
		enabled: !!snapshotId,
		staleTime: 60_000,
	})
}
