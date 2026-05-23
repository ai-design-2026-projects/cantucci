import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { logoutFetcher } from '@/api/services/auth'
import { useAuthStore } from '@/store/useAuthStore'
import { useConversationStore } from '@/store/useConversationStore'
import { useSnapshotStore } from '@/store/useSnapshotStore'

/**
 * Bundles the authenticated user and logout side effects for the header menu.
 *
 * @returns The current user plus a logout handler.
 */
export function useUserMenu() {
	const { user, setUser } = useAuthStore()
	const { setActiveConversationId, clearAnonConversationId } = useConversationStore()
	const { setActiveSnapshotId } = useSnapshotStore()
	const queryClient = useQueryClient()
	const navigate = useNavigate()

	const { mutate } = useMutation({
		mutationFn: logoutFetcher,
		onSuccess: () => {
			setUser(null)
			setActiveConversationId(null)
			clearAnonConversationId()
			setActiveSnapshotId(null)
			queryClient.clear()
			navigate('/login')
		},
	})

	const logout = () => mutate()

	return { user, logout }
}