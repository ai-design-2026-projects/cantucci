import { MessageBubble } from './MessageBubble'
import { LoadingBubble } from './LoadingBubble'
import { EmptyChatState } from './EmptyChatState'
import { useChatScroll } from '../hooks/useChatScroll'
import type { MessageDto } from '@/api/dto/conversations'

/**
 * Scrollable list of chat messages. Auto-scrolls to the bottom on new messages.
 * Shows EmptyChatState when no messages exist.
 *
 * @param messages  - Array of messages to render.
 * @param isLoading - When true, appends the LoadingBubble at the bottom.
 * @param isError   - Passed through to LoadingBubble for error expression.
 * @returns Scrollable message container.
 */
export function MessageList({
	messages,
	isLoading,
	isError,
}: {
	messages: MessageDto[]
	isLoading: boolean
	isError: boolean
}) {
	const scrollRef = useChatScroll(messages.length + (isLoading ? 1 : 0))

	return (
		<div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto scrollbar-styled px-4 py-4 flex flex-col gap-3">
			{messages.length === 0 && !isLoading ? (
				<EmptyChatState />
			) : (
				<>
					{messages.map((m) => (
						<MessageBubble key={m.id} message={m} />
					))}
					<LoadingBubble isLoading={isLoading} isError={isError} />
				</>
			)}
		</div>
	)
}
