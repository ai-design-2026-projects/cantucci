import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { createConversationFetcher } from '@/api/conversations'
import { useAuthStore } from '@/store/useAuthStore'
import { useConversationStore } from '@/store/useConversationStore'
import { useConversationsList } from './hooks/useConversationsList'
import { useDeleteConversation } from './hooks/useDeleteConversation'
import { ConversationListItem } from './components/ConversationListItem'
import { AuthGatePrompt } from './components/AuthGatePrompt'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'

interface HistoryDrawerProps {
  open: boolean
  onClose: () => void
}

/**
 * Slide-in sheet showing the authenticated user's conversation history.
 * Anonymous users see an auth gate prompt.
 *
 * @param open    - Controls sheet visibility.
 * @param onClose - Called when the sheet should close.
 * @returns Radix-based sheet with conversation list or auth prompt.
 */
export function HistoryDrawer({ open, onClose }: HistoryDrawerProps) {
  const user = useAuthStore((s) => s.user)
  const { setActiveConversationId } = useConversationStore()
  const navigate = useNavigate()
  const { conversationId: activeId } = useParams<{ conversationId: string }>()
  const queryClient = useQueryClient()

  const { data: conversations = [], isLoading } = useConversationsList(!!user && open)
  const { mutate: deleteConversation } = useDeleteConversation()

  const { mutate: newConversation, isPending: creating } = useMutation({
    mutationFn: createConversationFetcher,
    onSuccess: (conv) => {
      setActiveConversationId(conv.id)
      navigate(`/c/${conv.id}`)
      onClose()
      queryClient.invalidateQueries({ queryKey: ['conversations-list'] })
    },
  })

  function handleSelect(conversationId: string) {
    setActiveConversationId(conversationId)
    navigate(`/c/${conversationId}`)
    onClose()
  }

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>History</SheetTitle>
        </SheetHeader>

        {!user ? (
          <AuthGatePrompt />
        ) : (
          <div className="flex flex-col flex-1 overflow-hidden">
            <div className="flex-1 overflow-y-auto">
              {isLoading && (
                <p className="text-sm text-[var(--color-muted)] px-4 py-3">Loading…</p>
              )}
              {!isLoading && conversations.length === 0 && (
                <p className="text-sm text-[var(--color-muted)] px-4 py-3">No conversations yet</p>
              )}
              {conversations.map((conv) => (
                <ConversationListItem
                  key={conv.id}
                  conversation={conv}
                  isActive={conv.id === activeId}
                  onSelect={() => handleSelect(conv.id)}
                  onDelete={() => deleteConversation(conv.id)}
                />
              ))}
            </div>
            <div className="p-4 border-t border-[var(--color-border)]">
              <Button
                variant="outline"
                className="w-full gap-2"
                onClick={() => newConversation()}
                disabled={creating}
              >
                <Plus className="h-4 w-4" />
                New Conversation
              </Button>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
