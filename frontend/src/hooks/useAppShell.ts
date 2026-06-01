import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getConversationFetcher } from '@/api/services/conversations'
import { useAuthHydration } from '@/hooks/useAuthHydration'
import { useAuthStore } from '@/store/useAuthStore'
import { useConversationStore } from '@/store/useConversationStore'
import { useThemeStore } from '@/store/useThemeStore'

/**
 * Bootstraps the app shell state and restores the active conversation.
 *
 * @returns The current conversation route id, if any.
 */
export function useAppShell() {
	const { conversationId } = useParams<{ conversationId: string }>()
	const navigate = useNavigate()

	useAuthHydration()

	const { status } = useAuthStore()
	const { initTheme } = useThemeStore()
	const {
		setActiveConversationId,
		loadAnonConversationId,
		saveAnonConversationId,
		clearAnonConversationId,
	} = useConversationStore()

	useEffect(() => {
		initTheme()
	}, [initTheme])

	useEffect(() => {
		if (conversationId) {
			setActiveConversationId(conversationId)
			return
		}

		if (status !== 'unauthenticated') return

		const storedId = loadAnonConversationId()

		if (storedId) {
			getConversationFetcher(storedId)
				.then(() => {
					saveAnonConversationId(storedId)
					navigate(`/conversation/${storedId}`, { replace: true })
				})
				.catch(() => {
					clearAnonConversationId()
				})
		}
	}, [
		conversationId,
		status,
		setActiveConversationId,
		loadAnonConversationId,
		saveAnonConversationId,
		clearAnonConversationId,
		navigate,
	])

	return { conversationId }
}