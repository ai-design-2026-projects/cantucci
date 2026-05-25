import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { registerFetcher } from '@/api/services/auth'
import { createConversationFetcher } from '@/api/services/conversations'
import { useAuthStore } from '@/store/useAuthStore'
import { useConversationStore } from '@/store/useConversationStore'

/**
 * Mutation hook for registering a new account. On success, updates auth state,
 * creates a new conversation, and navigates directly to it. Falls back to the
 * home page if conversation creation fails.
 *
 * @returns Mutation object with mutate, isPending, error.
 */
export function useRegister() {
	const setUser = useAuthStore((s) => s.setUser)
	const setActiveConversationId = useConversationStore((s) => s.setActiveConversationId)
	const navigate = useNavigate()

	return useMutation({
		mutationFn: ({ email, password }: { email: string; password: string }) =>
			registerFetcher(email, password),
		onSuccess: async (data) => {
			setUser(data.user)
			try {
				const conv = await createConversationFetcher()
				setActiveConversationId(conv.id)
				navigate(`/conversation/${conv.id}`)
			} catch {
				navigate('/')
			}
		},
	})
}
