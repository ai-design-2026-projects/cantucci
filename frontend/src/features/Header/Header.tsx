import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { BrandMark } from './components/BrandMark'
import { ThemeToggle } from './components/ThemeToggle'
import { UserMenu, SignInButton } from './components/UserMenu'
import { HistoryButton } from './components/HistoryButton'
import { EvolutionMapButton } from './components/EvolutionMapButton'
import { HistoryDrawer } from '@/features/History/HistoryDrawer'
import { EvolutionMapModal } from '@/features/EvolutionMap/EvolutionMapModal'

/**
 * Fixed top header. Contains the brand mark, evolution map button (when in a
 * conversation), history drawer trigger, theme toggle, and auth controls.
 *
 * @returns Fixed-position full-width header bar.
 */
export function Header() {
  const [historyOpen, setHistoryOpen] = useState(false)
  const [evolutionOpen, setEvolutionOpen] = useState(false)
  const user = useAuthStore((s) => s.user)
  const { conversationId } = useParams<{ conversationId: string }>()

  return (
    <>
      <header className="fixed top-0 left-0 right-0 z-30 h-14 flex items-center justify-between px-4 bg-[var(--color-surface)] border-b border-[var(--color-border)]">
        <BrandMark />

        <div className="flex items-center gap-1">
          {conversationId && (
            <EvolutionMapButton
              onClick={() => setEvolutionOpen(true)}
              disabled={!conversationId}
            />
          )}
          <HistoryButton onClick={() => setHistoryOpen(true)} />
          <ThemeToggle />
          {user ? <UserMenu /> : <SignInButton />}
        </div>
      </header>

      <HistoryDrawer open={historyOpen} onClose={() => setHistoryOpen(false)} />
      {conversationId && (
        <EvolutionMapModal
          open={evolutionOpen}
          onClose={() => setEvolutionOpen(false)}
          conversationId={conversationId}
        />
      )}
    </>
  )
}
