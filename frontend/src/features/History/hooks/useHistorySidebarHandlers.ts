import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createConversationFetcher } from '@/api/services/conversations'
import { useAuthStore } from '@/store/useAuthStore'
import { useConversationStore } from '@/store/useConversationStore'
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
	const user = useAuthStore((s) => s.user)
	const saveAnonConversationId = useConversationStore((s) => s.saveAnonConversationId)
	const { mutate: deleteConversation } = useDeleteConversation()

	const { mutate: createConversation, isPending: creating } = useMutation({
		mutationFn: createConversationFetcher,
		onSuccess: (conversation) => {
			navigate(`/conversation/${conversation.id}`)
			if (user) {
				setActiveConversationId(conversation.id)
				queryClient.invalidateQueries({ queryKey: ['conversations-list'] })
			} else {
				saveAnonConversationId(conversation.id)
			}
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