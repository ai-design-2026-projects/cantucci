import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { loginFetcher } from '@/api/services/auth'
import { useAuthStore } from '@/store/useAuthStore'
import { useConversationStore } from '@/store/useConversationStore'

/**
 * Mutation hook for logging in. On success, updates auth state, clears any
 * anonymous conversation from localStorage, and navigates to the WelcomePage
 * so the user can start or resume a conversation.
 *
 * @returns Mutation object with mutate, isPending, error.
 */
export function useLogin() {
	const setUser = useAuthStore((s) => s.setUser)
	const clearAnonConversationId = useConversationStore((s) => s.clearAnonConversationId)
	const navigate = useNavigate()

	return useMutation({
		mutationFn: ({ email, password }: { email: string; password: string }) =>
			loginFetcher(email, password),
		onSuccess: (data) => {
			setUser(data.user)
			clearAnonConversationId()
			navigate('/')
		},
	})
}
