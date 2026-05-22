import { History } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface HistoryButtonProps {
  onClick: () => void
}

/**
 * Icon button that opens the conversation history drawer.
 *
 * @param onClick - Handler to open the history sheet.
 * @returns Ghost icon button.
 */
export function HistoryButton({ onClick }: HistoryButtonProps) {
  return (
    <Button variant="ghost" size="icon" onClick={onClick} aria-label="Conversation history">
      <History className="h-4 w-4" />
    </Button>
  )
}
