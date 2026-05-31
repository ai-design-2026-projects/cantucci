import { useQuery } from '@tanstack/react-query'
import { getConversationFetcher } from '@/api/services/conversations'
import type { ConversationDto } from '@/api/dto/conversations'

/**
 * Fetch all messages for a conversation (no limit). Used by the eval transcript
 * viewer where the full history must be shown regardless of length.
 *
 * @param conversationId - Conversation UUID string, or undefined when not active.
 * @returns TanStack Query result wrapping ConversationDto with all messages.
 */
export function useFullConversation(conversationId: string | undefined) {
    return useQuery<ConversationDto>({
        queryKey: ['conversation', conversationId, 'full'],
        queryFn: () => getConversationFetcher(conversationId!, null),
        enabled: !!conversationId,
        staleTime: 30_000,
    })
}
