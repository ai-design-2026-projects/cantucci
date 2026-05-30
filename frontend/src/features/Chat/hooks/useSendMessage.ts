import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { sendMessageFetcher } from '@/api/services/conversations'
import { OPERATION_LABELS } from '@/lib/constants'
import type { ConversationDto, MessageDto } from '@/api/dto/conversations'

/**
 * Mutation hook for sending a user message and handling the response.
 * Optimistically appends the user message to the cache so it appears
 * immediately, then invalidates on success to load the assistant reply.
 *
 * @param conversationId - Conversation UUID to send the message to.
 * @returns Mutation object with mutate, isPending, isError.
 */
export function useSendMessage(conversationId: string) {
	const queryClient = useQueryClient()
	const queryKey = ['conversation', conversationId]
	const zeroSnapshotId = '00000000-0000-0000-0000-000000000000'

	return useMutation({
		mutationFn: (content: string) => sendMessageFetcher(conversationId, content),
		onMutate: async (content: string) => {
			await queryClient.cancelQueries({ queryKey })
			const previous = queryClient.getQueryData<ConversationDto>(queryKey)
			const optimisticMessage: MessageDto = {
				id: crypto.randomUUID(),
				role: 'user',
				content,
				created_at: new Date().toISOString(),
			}
			queryClient.setQueryData<ConversationDto>(queryKey, (old) =>
				old ? { ...old, messages: [...old.messages, optimisticMessage] } : old
			)
			return { previous }
		},
		onSuccess: (data) => {
			const oldSnapshotId = queryClient.getQueryData<ConversationDto>(queryKey)?.current_cluster_snapshot_id
			const newSnapshotId = data.cluster_snapshot_id
			const normalizedSnapshotId = newSnapshotId && newSnapshotId !== zeroSnapshotId ? newSnapshotId : null
			queryClient.setQueryData<ConversationDto>(queryKey, (old) =>
				old
					? {
						...old,
						current_cluster_snapshot_id: normalizedSnapshotId ?? old.current_cluster_snapshot_id,
						messages: [...old.messages, data.message],
					}
					: old
			)

			const isNewSnapshot = !!normalizedSnapshotId && normalizedSnapshotId !== oldSnapshotId

			if (isNewSnapshot) {
				queryClient.invalidateQueries({ queryKey: ['snapshot', normalizedSnapshotId] })
				queryClient.invalidateQueries({ queryKey: ['snapshot-graph', conversationId] })
				const snapshotData = queryClient.getQueryData<{ operation?: string }>(['snapshot', normalizedSnapshotId])
				const opLabel = snapshotData?.operation ? OPERATION_LABELS[snapshotData.operation] ?? snapshotData.operation : 'New snapshot'
				toast.success(`Snapshot updated: ${opLabel}`)
			}
		},
		onError: (err: Error, _content, context) => {
			if (context?.previous) {
				queryClient.setQueryData(queryKey, context.previous)
			}
			toast.error(err.message || 'Something went wrong. Poppy is sad 😢')
		},
	})
}
