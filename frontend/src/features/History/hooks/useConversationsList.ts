import { useQuery } from '@tanstack/react-query'
import { listConversationsFetcher } from '@/api/services/conversations'
import type { ConversationDto } from '@/api/dto/conversations'

/**
 * Fetch hook for loading the authenticated user's conversation list.
 *
 * @param enabled - Only fetches when true (i.e., user is authenticated).
 * @returns TanStack Query result wrapping ConversationDto[].
 */
export function useConversationsList(enabled: boolean) {
	return useQuery<ConversationDto[]>({
		queryKey: ['conversations-list'],
		queryFn: listConversationsFetcher,
		enabled,
		staleTime: 30_000,
	})
}
