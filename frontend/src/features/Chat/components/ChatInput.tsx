import { useState, useRef } from 'react'
import { Send } from 'lucide-react'
import { Button } from '@/components/button'

interface ChatInputProps {
  onSend: (content: string) => void
  disabled: boolean
}

/**
 * Textarea input bar for composing and sending messages.
 * Submits on Enter (without shift) or Cmd/Ctrl+Enter.
 *
 * @param onSend   - Called with the trimmed message content.
 * @param disabled - Disables input while a turn is in flight.
 * @returns Sticky input bar at the bottom of the chat panel.
 */
export function ChatInput({ onSend, disabled }: ChatInputProps) {
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
        disabled={disabled || !value.trim()}
        size="icon"
        className="flex-shrink-0 self-end"
      >
        <Send className="h-4 w-4" />
      </Button>
    </div>
  )
}
