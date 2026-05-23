import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { PanelLeftOpen, PanelLeftClose, Plus } from 'lucide-react'
import { useAuthStore } from '@/store/useAuthStore'
import { useConversationStore } from '@/store/useConversationStore'
import { createConversationFetcher } from '@/api/services/conversations'
import { useConversationsList } from './hooks/useConversationsList'
import { useDeleteConversation } from './hooks/useDeleteConversation'
import { ConversationListItem } from './components/ConversationListItem'
import { AuthGatePrompt } from './components/AuthGatePrompt'
import { Button } from '@/components/button'

const STORAGE_KEY = 'cinepal_history_open'

/**
 * Collapsible left sidebar showing the authenticated user's conversation history.
 * Default state is collapsed. Toggle persists to localStorage.
 *
 * @returns Animated left-column sidebar with conversation list or auth prompt.
 */
export function HistorySidebar() {
  const [open, setOpen] = useState(() => localStorage.getItem(STORAGE_KEY) === 'true')

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
      queryClient.invalidateQueries({ queryKey: ['conversations-list'] })
    },
  })

  function toggle() {
    const next = !open
    setOpen(next)
    localStorage.setItem(STORAGE_KEY, String(next))
  }

  function handleSelect(conversationId: string) {
    setActiveConversationId(conversationId)
    navigate(`/c/${conversationId}`)
  }

  return (
    <div
      className={`flex-shrink-0 flex flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] transition-all duration-200 overflow-hidden ${open ? 'w-72' : 'w-14'}`}
    >
      <div className={`flex items-center border-b border-[var(--color-border)] h-12 flex-shrink-0 ${open ? 'justify-between px-3' : 'justify-center'}`}>
        {open && (
          <span className="text-sm font-medium text-[var(--color-text)]">History</span>
        )}
        <Button variant="ghost" size="icon" onClick={toggle} className="h-8 w-8">
          {open ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
        </Button>
      </div>

      {open ? (
        <>
          {!user ? (
            <AuthGatePrompt />
          ) : (
            <>
              <div className="flex-1 overflow-y-auto">
                {isLoading && (
                  <p className="text-xs text-[var(--color-muted)] px-4 py-3">Loading…</p>
                )}
                {!isLoading && conversations.length === 0 && (
                  <p className="text-xs text-[var(--color-muted)] px-4 py-3">No conversations yet</p>
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
              <div className="p-3 border-t border-[var(--color-border)]">
                <Button
                  variant="outline"
                  className="w-full gap-2 text-xs h-8"
                  onClick={() => newConversation()}
                  disabled={creating}
                >
                  <Plus className="h-3.5 w-3.5" />
                  New Conversation
                </Button>
              </div>
            </>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center gap-2 pt-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => newConversation()}
            disabled={creating || !user}
            title="New conversation"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  )
}
