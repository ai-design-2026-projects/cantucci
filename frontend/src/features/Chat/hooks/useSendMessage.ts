import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { sendMessageFetcher } from '@/api/conversations'
import { useSnapshotStore } from '@/store/useSnapshotStore'
import { OPERATION_LABELS } from '@/lib/constants'

/**
 * Mutation hook for sending a user message and handling the response.
 * On success, invalidates the conversation query and updates the active
 * snapshot if the turn produced a new one.
 *
 * @param conversationId - Conversation UUID to send the message to.
 * @returns Mutation object with mutate, isPending, isError.
 */
export function useSendMessage(conversationId: string) {
  const queryClient = useQueryClient()
  const { activeSnapshotId, setActiveSnapshotId } = useSnapshotStore()

  return useMutation({
    mutationFn: (content: string) => sendMessageFetcher(conversationId, content),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] })

      const newSnapshotId = data.cluster_snapshot_id
      const isNewSnapshot =
        newSnapshotId &&
        newSnapshotId !== '00000000-0000-0000-0000-000000000000' &&
        newSnapshotId !== activeSnapshotId

      if (isNewSnapshot) {
        setActiveSnapshotId(newSnapshotId)
        queryClient.invalidateQueries({ queryKey: ['snapshot', newSnapshotId] })
        queryClient.invalidateQueries({ queryKey: ['snapshot-graph', conversationId] })
        const snapshotData = queryClient.getQueryData<{ operation?: string }>(['snapshot', newSnapshotId])
        const opLabel = snapshotData?.operation ? OPERATION_LABELS[snapshotData.operation] ?? snapshotData.operation : 'New snapshot'
        toast.success(`Snapshot updated: ${opLabel}`)
      }
    },
    onError: (err: Error) => {
      toast.error(err.message || 'Something went wrong. Poppy is sad 😢')
    },
  })
}
