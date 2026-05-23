import { useQuery } from '@tanstack/react-query'
import { getSnapshotGraphFetcher } from '@/api/services/snapshots'
import type { ClusterSnapshotGraphDto } from '@/api/dto/snapshots'

/**
 * Fetch hook for loading all cluster snapshot nodes for a conversation.
 * Used to render the force-directed evolution map.
 *
 * @param conversationId - Conversation UUID, or undefined when no conversation is active.
 * @returns TanStack Query result wrapping ClusterSnapshotGraphDto.
 */
export function useSnapshotGraph(conversationId: string | undefined) {
	return useQuery<ClusterSnapshotGraphDto>({
		queryKey: ['snapshot-graph', conversationId],
		queryFn: () => getSnapshotGraphFetcher(conversationId!),
		enabled: !!conversationId,
		staleTime: 10_000,
	})
}
