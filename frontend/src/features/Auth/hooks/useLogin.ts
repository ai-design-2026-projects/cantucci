import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { loginFetcher } from '@/api/services/auth'
import { useAuthStore } from '@/store/useAuthStore'

/**
 * Mutation hook for logging in. On success, updates auth state and
 * navigates to the home page.
 *
 * @returns Mutation object with mutate, isPending, error.
 */
export function useLogin() {
	const setUser = useAuthStore((s) => s.setUser)
	const navigate = useNavigate()

	return useMutation({
		mutationFn: ({ email, password }: { email: string; password: string }) =>
			loginFetcher(email, password),
		onSuccess: (data) => {
			setUser(data.user)
			navigate('/')
		},
	})
}
