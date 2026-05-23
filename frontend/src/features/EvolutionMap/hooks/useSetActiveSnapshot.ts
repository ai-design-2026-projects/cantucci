import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { patchConversationFetcher } from '@/api/services/conversations'
import { useSnapshotStore } from '@/store/useSnapshotStore'

/**
 * Mutation hook that sets the active cluster snapshot for a conversation.
 * On success, updates the Zustand store, URL search param, and invalidates
 * the conversation query so useSyncConversationSnapshot stays in sync.
 *
 * @param conversationId - Conversation UUID.
 * @returns Mutation object with mutate, isPending.
 */
export function useSetActiveSnapshot(conversationId: string) {
	const queryClient = useQueryClient()
	const { setActiveSnapshotId } = useSnapshotStore()
	const [, setSearchParams] = useSearchParams()

	return useMutation({
		mutationFn: (snapshotId: string) =>
			patchConversationFetcher(conversationId, snapshotId),
		onSuccess: (_, snapshotId) => {
			setActiveSnapshotId(snapshotId)
			setSearchParams({ snapshot: snapshotId }, { replace: true })
			queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] })
		},
		onError: (err: Error) => {
			toast.error(err.message || 'Could not switch snapshot')
		},
	})
}
