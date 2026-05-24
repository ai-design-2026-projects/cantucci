import { useRef, useState } from 'react'

type SubmitMessage = (content: string) => void

/**
 * Owns the chat input state, textarea ref, and submit/input handlers.
 *
 * @param onSend - Called with the trimmed message content.
 * @param disabled - Disables submission while a turn is in flight.
 * @returns Controlled value, textarea ref, and input handlers.
 */
export function useChatInput(onSend: SubmitMessage, disabled: boolean) {
	const [value, setValue] = useState('')
	const textareaRef = useRef<HTMLTextAreaElement>(null)

	function submit() {
		const text = value.trim()
		if (!text || disabled) return
		onSend(text)
		setValue('')
		if (textareaRef.current) {
			textareaRef.current.style.height = 'auto'
		}
	}

	function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
		if ((e.key === 'Enter' && !e.shiftKey) || (e.key === 'Enter' && (e.metaKey || e.ctrlKey))) {
			e.preventDefault()
			submit()
		}
	}

	function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
		setValue(e.target.value)
		const el = e.target
		el.style.height = 'auto'
		el.style.height = `${Math.min(el.scrollHeight, 160)}px`
	}

	return {
		value,
		textareaRef,
		handleInput,
		handleKeyDown,
		submit,
		canSubmit: !disabled && value.trim().length > 0,
	}
}