import { apiClient } from '../client'
import type { ConversationDto, SendMessageResponse } from '../dto/conversations'
import type { ClusterSnapshotGraphDto } from '../dto/snapshots'

/**
 * Create a new conversation (anonymous or authenticated).
 *
 * @returns Full ConversationDto with empty messages list.
 */
export async function createConversationFetcher(): Promise<ConversationDto> {
    return apiClient<ConversationDto>('/conversations', { method: 'POST' })
}

/**
 * Fetch a conversation with its messages.
 *
 * @param conversationId - Conversation UUID.
 * @param limit          - Maximum messages to return. Pass null to fetch all.
 * @returns ConversationDto.
 */
export async function getConversationFetcher(conversationId: string): Promise<ConversationDto> {
    return apiClient<ConversationDto>(`/conversations/${conversationId}`)
}

/**
 * List all conversations owned by the authenticated user, newest first.
 * Each entry includes all messages for preview display.
 *
 * @returns Array of ConversationDto.
 */
export async function listConversationsFetcher(): Promise<ConversationDto[]> {
    return apiClient<ConversationDto[]>('/conversations')
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
 * Open a Server-Sent Events stream for real-time turn progress updates.
 *
 * Returns an EventSource connected to GET /conversations/{id}/events.
 * The caller is responsible for closing it via `source.close()`.
 *
 * @param conversationId - Conversation UUID.
 * @returns Native EventSource instance.
 */
export function openConversationEventStream(conversationId: string): EventSource {
    return new EventSource(`/conversations/${conversationId}/events`)
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

/**
 * Update a conversation's active cluster snapshot.
 *
 * @param conversationId           - Conversation UUID.
 * @param currentClusterSnapshotId - New active snapshot UUID, or null to detach.
 * @returns Updated ConversationDto.
 */
export async function patchConversationFetcher(
    conversationId: string,
    currentClusterSnapshotId: string | null,
): Promise<ConversationDto> {
    return apiClient<ConversationDto>(`/conversations/${conversationId}`, {
        method: 'PATCH',
        body: JSON.stringify({ current_cluster_snapshot_id: currentClusterSnapshotId }),
    })
}

/**
 * Fetch all cluster snapshot nodes for a conversation as a directed acyclic graph.
 *
 * @param conversationId - Conversation UUID.
 * @returns ClusterSnapshotGraphDto with all snapshot nodes.
 */
export async function getSnapshotGraphFetcher(conversationId: string): Promise<ClusterSnapshotGraphDto> {
    return apiClient<ClusterSnapshotGraphDto>(`/conversations/${conversationId}/snapshot-graph`)
}
