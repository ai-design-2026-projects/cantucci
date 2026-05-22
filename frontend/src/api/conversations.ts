import { apiClient } from './client'
import type {
  ConversationDto,
  ConversationSummaryDto,
  SendMessageResponse,
} from '@/lib/types'

/**
 * Create a new conversation (anonymous or authenticated).
 *
 * @returns Full ConversationDto with empty messages list.
 */
export async function createConversationFetcher(): Promise<ConversationDto> {
  return apiClient<ConversationDto>('/conversations', { method: 'POST' })
}

/**
 * Fetch a conversation with its most recent messages.
 *
 * @param conversationId - Conversation UUID.
 * @returns ConversationDto.
 */
export async function getConversationFetcher(conversationId: string): Promise<ConversationDto> {
  return apiClient<ConversationDto>(`/conversations/${conversationId}`)
}

/**
 * List all conversations owned by the authenticated user, newest first.
 *
 * @returns Array of ConversationSummaryDto.
 */
export async function listConversationsFetcher(): Promise<ConversationSummaryDto[]> {
  return apiClient<ConversationSummaryDto[]>('/conversations')
}

/**
 * Send a user message and receive the assistant reply.
 *
 * @param conversationId - Target conversation UUID.
 * @param content        - User message text.
 * @returns SendMessageResponse with the assistant message and cluster snapshot ID.
 */
export async function sendMessageFetcher(
  conversationId: string,
  content: string,
): Promise<SendMessageResponse> {
  return apiClient<SendMessageResponse>(`/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

/**
 * Delete a conversation owned by the authenticated user.
 *
 * @param conversationId - Conversation UUID to delete.
 * @returns void
 */
export async function deleteConversationFetcher(conversationId: string): Promise<void> {
  return apiClient<void>(`/conversations/${conversationId}`, { method: 'DELETE' })
}
