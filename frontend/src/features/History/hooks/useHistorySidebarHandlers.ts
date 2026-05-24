import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createConversationFetcher } from '@/api/services/conversations'
import { useDeleteConversation } from './useDeleteConversation'

/**
 * Builds the sidebar event handlers and mutation actions.
 *
 * @param state - Sidebar state setters used by the handlers.
 * @returns Toggle, select, create, and delete handlers.
 */
export function useHistorySidebarHandlers({
	open,
	setOpen,
	setActiveConversationId,
}: {
	open: boolean
	setOpen: (open: boolean) => void
	setActiveConversationId: (conversationId: string | null) => void
}) {
	const navigate = useNavigate()
	const queryClient = useQueryClient()
	const { mutate: deleteConversation } = useDeleteConversation()

	const { mutate: createConversation, isPending: creating } = useMutation({
		mutationFn: createConversationFetcher,
		onSuccess: (conversation) => {
			setActiveConversationId(conversation.id)
			navigate(`/conversation/${conversation.id}`)
			queryClient.invalidateQueries({ queryKey: ['conversations-list'] })
		},
	})

	function toggleSidebar() {
		const next = !open
		setOpen(next)
		localStorage.setItem('cinepal_history_open', String(next))
	}

	function selectConversation(conversationId: string) {
		setActiveConversationId(conversationId)
		navigate(`/conversation/${conversationId}`)
	}

	return {
		toggleSidebar,
		selectConversation,
		createConversation: () => createConversation(),
		deleteConversation,
		creating,
	}
}