import { Trash2 } from 'lucide-react'
import { Button } from '@/components/button'
import { relativeTime } from '@/lib/utils'
import type { ConversationDto } from '@/api/dto/conversations'

interface ConversationListItemProps {
  conversation: ConversationDto
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
}

/**
 * Single conversation entry in the history drawer.
 * Shows the preview message snippet and relative timestamp.
 *
 * @param conversation - Conversation summary to display.
 * @param isActive     - Highlights the currently loaded conversation.
 * @param onSelect     - Loads this conversation.
 * @param onDelete     - Deletes this conversation.
 * @returns List item with select and delete actions.
 */
export function ConversationListItem({
  conversation,
  isActive,
  onSelect,
  onDelete,
}: ConversationListItemProps) {
  return (
    <div
      className={`group flex items-start gap-2 px-4 py-3 cursor-pointer border-b border-[var(--color-border)] last:border-0 transition-colors ${
        isActive ? 'bg-[var(--color-elevated)]' : 'hover:bg-[var(--color-elevated)]'
      }`}
      onClick={onSelect}
    >
      <div className="flex-1 min-w-0">
        <p className="text-sm text-[var(--color-text)] truncate">
          {conversation.messages[0]?.content ?? 'Empty conversation'}
        </p>
        <p className="text-xs text-[var(--color-muted)] mt-0.5">
          {relativeTime(conversation.created_at)}
        </p>
      </div>
      <Button
        variant="ghost"
        size="icon"
        className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity h-7 w-7"
        onClick={(e) => { e.stopPropagation(); onDelete() }}
      >
        <Trash2 className="h-3.5 w-3.5 text-[var(--color-muted)]" />
      </Button>
    </div>
  )
}
