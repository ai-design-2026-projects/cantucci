import { useConversation } from './hooks/useConversation'
import { useSendMessage } from './hooks/useSendMessage'
import { useConversationProgress } from './hooks/useConversationProgress'
import { MessageList } from './components/MessageList'
import { ChatInput } from './components/ChatInput'
import { STEP_LABELS, STEP_EXPRESSIONS } from '@/lib/constants'

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
	const { currentStep } = useConversationProgress(conversationId)

	const messages = conversation?.messages ?? []
	const currentStepLabel = currentStep ? STEP_LABELS[currentStep] : undefined
	const currentStepExpression = currentStep ? STEP_EXPRESSIONS[currentStep] : undefined

	return (
		<div className="flex flex-col h-full min-h-0">
			<MessageList
				messages={messages}
				isLoading={isPending || convLoading}
				isError={isError}
				currentStepLabel={currentStepLabel}
				currentStepExpression={currentStepExpression}
			/>
			<ChatInput
				onSend={(content) => sendMessage(content)}
				disabled={isPending}
			/>
		</div>
	)
}
