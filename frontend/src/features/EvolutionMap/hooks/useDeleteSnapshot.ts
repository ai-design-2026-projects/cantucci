import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { deleteSnapshotFetcher } from '@/api/snapshots'
import { useSnapshotStore } from '@/store/useSnapshotStore'

/**
 * Mutation hook for deleting a cluster snapshot.
 * Refetches the snapshot graph on success.
 * Shows a toast with a sad Poppy message on 409 conflict (has children).
 *
 * @param conversationId - Conversation UUID used to invalidate the graph query.
 * @returns Mutation object with mutate, isPending.
 */
export function useDeleteSnapshot(conversationId: string) {
  const queryClient = useQueryClient()
  const { activeSnapshotId, setActiveSnapshotId } = useSnapshotStore()

  return useMutation({
    mutationFn: (snapshotId: string) => deleteSnapshotFetcher(snapshotId),
    onSuccess: (_data, snapshotId) => {
      queryClient.invalidateQueries({ queryKey: ['snapshot-graph', conversationId] })
      if (activeSnapshotId === snapshotId) {
        setActiveSnapshotId(null)
      }
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
