import { useConversation } from './hooks/useConversation'
import { useSendMessage } from './hooks/useSendMessage'
import { useSyncConversationSnapshot } from './hooks/useSyncConversationSnapshot'
import { MessageList } from './components/MessageList'
import { ChatInput } from './components/ChatInput'

/**
 * Left-panel chat interface. Loads the conversation, renders the message list,
 * and syncs the active snapshot store whenever the conversation's head snapshot changes.
 *
 * @param conversationId - Active conversation UUID.
 * @returns Flex-column chat layout with message list + input bar.
 */
export function ChatPanel({ conversationId }: { conversationId: string }) {
	const { data: conversation, isLoading: convLoading } = useConversation(conversationId)
	const { mutate: sendMessage, isPending, isError } = useSendMessage(conversationId)

	useSyncConversationSnapshot(conversation?.current_cluster_snapshot_id)

	const messages = conversation?.messages ?? []

	return (
		<div className="flex flex-col h-full min-h-0">
			<MessageList
				messages={messages}
				isLoading={isPending || convLoading}
				isError={isError}
			/>
			<ChatInput
				onSend={(content) => sendMessage(content)}
				disabled={isPending}
			/>
		</div>
	)
}
