import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { useConversationStore } from '@/store/useConversationStore'
import { useConversationsList } from './useConversationsList'

const STORAGE_KEY = 'cinepal_history_open'

/**
 * Collects the sidebar state and query data used by the history panel.
 *
 * @returns Sidebar open state, auth state, route state, and conversations.
 */
export function useHistorySidebarData() {
	const [open, setOpen] = useState(() => localStorage.getItem(STORAGE_KEY) === 'true')
	const user = useAuthStore((state) => state.user)
	const { setActiveConversationId } = useConversationStore()
	const { conversationId: activeId } = useParams<{ conversationId: string }>()
	const { data: conversations = [], isLoading } = useConversationsList(!!user && open)

	return {
		open,
		setOpen,
		user,
		activeId,
		conversations,
		isLoading,
		setActiveConversationId,
	}
}