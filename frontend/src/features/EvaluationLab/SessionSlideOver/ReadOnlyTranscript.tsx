import { useFullConversation } from '../hooks/useFullConversation'
import { MessageList } from '@/features/Chat/components/MessageList'

interface ReadOnlyTranscriptProps {
    conversationId: string
}

/**
 * Read-only view of a conversation transcript. Fetches all messages (no limit)
 * so the full eval conversation is shown regardless of length.
 */
export function ReadOnlyTranscript({ conversationId }: ReadOnlyTranscriptProps) {
    const { data: conversation, isLoading, isError } = useFullConversation(conversationId)

    return (
        <div className="flex flex-col flex-1 min-h-0">
            <div className="px-4 py-3 border-b border-[var(--color-border)] shrink-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
                    Transcript
                </p>
            </div>
            <MessageList
                messages={conversation?.messages ?? []}
                isLoading={isLoading}
                isError={isError}
            />
        </div>
    )
}
