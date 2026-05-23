import { useQuery } from '@tanstack/react-query'
import { getConversationFetcher } from '@/api/services/conversations'
import type { ConversationDto } from '@/api/dto/conversations'

/**
 * Fetch hook for loading a conversation with its recent messages.
 *
 * @param conversationId - Conversation UUID string, or undefined when no conversation is active.
 * @returns TanStack Query result wrapping ConversationDto.
 */
export function useConversation(conversationId: string | undefined) {
	return useQuery<ConversationDto>({
		queryKey: ['conversation', conversationId],
		queryFn: () => getConversationFetcher(conversationId!),
		enabled: !!conversationId,
		staleTime: 0,
	})
}
