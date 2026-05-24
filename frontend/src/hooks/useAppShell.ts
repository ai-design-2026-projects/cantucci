import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { meFetcher } from '@/api/services/auth'
import { getConversationFetcher } from '@/api/services/conversations'
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

	const { setUser, setStatus } = useAuthStore()
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
		setStatus('loading')
		meFetcher().then((user) => setUser(user))
	}, [setUser, setStatus])

	useEffect(() => {
		if (conversationId) {
			setActiveConversationId(conversationId)
			return
		}

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
		setActiveConversationId,
		loadAnonConversationId,
		saveAnonConversationId,
		clearAnonConversationId,
		navigate,
	])

	return { conversationId }
}