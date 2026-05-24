import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { deleteSnapshotFetcher } from '@/api/services/snapshots'

/**
 * Mutation hook for deleting a cluster snapshot.
 * Invalidates the snapshot graph on success. Active snapshot reparenting is
 * the caller's responsibility (pass an onSuccess callback to mutate()).
 *
 * @param conversationId - Conversation UUID used to invalidate the graph query.
 * @returns Mutation object with mutate, isPending.
 */
export function useDeleteSnapshot(conversationId: string) {
	const queryClient = useQueryClient()

	return useMutation({
		mutationFn: (snapshotId: string) => deleteSnapshotFetcher(snapshotId),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['snapshot-graph', conversationId] })
			toast.success('Snapshot deleted')
		},
		onError: (err: Error) => {
			if (err.message.includes('child')) {
				toast.error('This snapshot has children — delete those first 🥺')
			} else {
				toast.error(err.message || 'Could not delete snapshot')
			}
		},
	})
}
