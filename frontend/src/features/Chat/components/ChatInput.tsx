import { Send } from 'lucide-react'
import { Button } from '@/components/button'
import { useChatInput } from '../hooks/useChatInput.ts'

/**
 * Textarea input bar for composing and sending messages.
 * Submits on Enter (without shift) or Cmd/Ctrl+Enter.
 *
 * @param onSend   - Called with the trimmed message content.
 * @param disabled - Disables input while a turn is in flight.
 * @returns Sticky input bar at the bottom of the chat panel.
 */
export function ChatInput({
	onSend,
	disabled,
}: {
	onSend: (content: string) => void
	disabled: boolean
}) {
	const { value, textareaRef, handleInput, handleKeyDown, submit, canSubmit } =
		useChatInput(onSend, disabled)

	return (
		<div className="flex gap-2 px-4 py-3 border-t border-[var(--color-border)] bg-[var(--color-bg)]">
			<textarea
				ref={textareaRef}
				value={value}
				onChange={handleInput}
				onKeyDown={handleKeyDown}
				disabled={disabled}
				placeholder="Ask Poppy something…"
				rows={1}
				className="flex-1 resize-none rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] placeholder:text-[var(--color-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] disabled:opacity-50 transition-colors overflow-hidden"
			/>
			<Button
				onClick={submit}
				disabled={!canSubmit}
				size="icon"
				className="flex-shrink-0 self-end"
			>
				<Send className="h-4 w-4" />
			</Button>
		</div>
	)
}
