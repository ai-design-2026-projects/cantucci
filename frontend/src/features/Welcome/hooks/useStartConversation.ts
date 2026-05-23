import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createConversationFetcher } from '@/api/services/conversations'

/**
 * Creates the welcome-screen conversation and navigates to it.
 *
 * @param user - Current auth user used to decide which store to update.
 * @param setActiveConversationId - Sets the active conversation for signed-in users.
 * @param saveAnonConversationId - Persists the conversation for anonymous users.
 * @returns A start action and pending state for the CTA button.
 */
export function useStartConversation({
	user,
	setActiveConversationId,
	saveAnonConversationId,
}: {
	user: { id: string } | null
	setActiveConversationId: (conversationId: string) => void
	saveAnonConversationId: (conversationId: string) => void
}) {
	const navigate = useNavigate()

	const { mutate, isPending } = useMutation({
		mutationFn: createConversationFetcher,
		onSuccess: (conversation) => {
			if (user) {
				setActiveConversationId(conversation.id)
			} else {
				saveAnonConversationId(conversation.id)
			}
			navigate(`/conversation/${conversation.id}`)
		},
	})

	return {
		startConversation: () => mutate(),
		isPending,
	}
}