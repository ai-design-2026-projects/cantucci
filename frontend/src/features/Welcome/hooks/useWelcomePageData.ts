import { useAuthStore } from '@/store/useAuthStore'
import { useConversationStore } from '@/store/useConversationStore'

/**
 * Collects the page data used by the welcome screen.
 *
 * @returns Auth and conversation store state required by the welcome flow.
 */
export function useWelcomePageData() {
	const user = useAuthStore((state) => state.user)
	const { saveAnonConversationId, setActiveConversationId } = useConversationStore()

	return {
		user,
		saveAnonConversationId,
		setActiveConversationId,
	}
}