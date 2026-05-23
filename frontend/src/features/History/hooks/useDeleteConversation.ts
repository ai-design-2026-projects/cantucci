import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { deleteConversationFetcher } from '@/api/services/conversations'

/**
 * Mutation hook for deleting a conversation from the history list.
 * Refetches the conversations list on success.
 *
 * @returns Mutation object with mutate(conversationId), isPending.
 */
export function useDeleteConversation() {
	const queryClient = useQueryClient()

	return useMutation({
		mutationFn: (conversationId: string) => deleteConversationFetcher(conversationId),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['conversations-list'] })
			toast.success('Conversation deleted')
		},
		onError: (err: Error) => {
			toast.error(err.message || 'Could not delete conversation')
		},
	})
}
