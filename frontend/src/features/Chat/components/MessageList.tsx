import { MessageBubble } from './MessageBubble'
import { LoadingBubble } from './LoadingBubble'
import { EmptyChatState } from './EmptyChatState'
import { useChatScroll } from '../hooks/useChatScroll'
import type { MessageDto } from '@/api/dto/conversations'
import type { MascotExpression } from '@/components/mascot'

/**
 * Scrollable list of chat messages. Auto-scrolls to the bottom on new messages.
 * Shows EmptyChatState when no messages exist.
 *
 * @param messages              - Array of messages to render.
 * @param isLoading             - When true, appends the LoadingBubble at the bottom.
 * @param isError               - Passed through to LoadingBubble for error expression.
 * @param currentStepLabel      - Live step label from SSE progress stream.
 * @param currentStepExpression - Live mascot expression matching the current step.
 * @returns Scrollable message container.
 */
export function MessageList({
	messages,
	isLoading,
	isError,
	currentStepLabel,
	currentStepExpression,
}: {
	messages: MessageDto[]
	isLoading: boolean
	isError: boolean
	currentStepLabel?: string
	currentStepExpression?: MascotExpression
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
					<LoadingBubble
						isLoading={isLoading}
						isError={isError}
						currentStepLabel={currentStepLabel}
						currentStepExpression={currentStepExpression}
					/>
				</>
			)}
		</div>
	)
}
