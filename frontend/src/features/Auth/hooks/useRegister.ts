import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { registerFetcher } from '@/api/services/auth'
import { useAuthStore } from '@/store/useAuthStore'

/**
 * Mutation hook for registering a new account. On success, updates auth state
 * and navigates to the home page.
 *
 * @returns Mutation object with mutate, isPending, error.
 */
export function useRegister() {
	const setUser = useAuthStore((s) => s.setUser)
	const navigate = useNavigate()

	return useMutation({
		mutationFn: ({ email, password }: { email: string; password: string }) =>
			registerFetcher(email, password),
		onSuccess: (data) => {
			setUser(data.user)
			navigate('/')
		},
	})
}
