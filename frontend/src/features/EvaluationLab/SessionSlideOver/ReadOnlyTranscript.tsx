import { useConversation } from '@/features/Chat/hooks/useConversation'
import { MessageList } from '@/features/Chat/components/MessageList'

interface ReadOnlyTranscriptProps {
    conversationId: string
}

/**
 * Read-only view of a conversation transcript.
 * Renders the message history without a chat input.
 */
export function ReadOnlyTranscript({ conversationId }: ReadOnlyTranscriptProps) {
    const { data: conversation, isLoading, isError } = useConversation(conversationId)

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
