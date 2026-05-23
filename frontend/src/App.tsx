import { useEffect } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useAuthStore } from './store/useAuthStore'
import { useThemeStore } from './store/useThemeStore'
import { useSnapshotStore } from './store/useSnapshotStore'
import { useConversationStore } from './store/useConversationStore'
import { meFetcher } from './api/auth'
import { getConversationFetcher } from './api/conversations'
import { Header } from './features/Header/Header'
import { ChatPanel } from './features/Chat/ChatPanel'
import { ClusterSnapshotTab } from './features/ClusterSnapshotTab/ClusterSnapshotTab'
import { WelcomePage } from './features/Welcome/WelcomePage'
import { FloatingMascot } from './components/mascot/FloatingMascot'
import { HistorySidebar } from './features/History/HistorySidebar'

/**
 * Root application layout. Handles auth hydration, theme init, anonymous
 * conversation restoration, and snapshot URL sync. Renders either the
 * Welcome screen or the two-column chat + snapshot layout.
 *
 * @returns Application shell.
 */
export default function App() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const [searchParams] = useSearchParams()
  const snapshotParam = searchParams.get('snapshot')

  const { setUser, setStatus } = useAuthStore()
  const { initTheme } = useThemeStore()
  const { setActiveSnapshotId } = useSnapshotStore()
  const { activeConversationId, setActiveConversationId, loadAnonConversationId, saveAnonConversationId } = useConversationStore()

  useEffect(() => {
    initTheme()
  }, [initTheme])

  useEffect(() => {
    setStatus('loading')
    meFetcher().then((user) => setUser(user))
  }, [setUser, setStatus])

  useEffect(() => {
    if (snapshotParam) {
      setActiveSnapshotId(snapshotParam)
    }
  }, [snapshotParam, setActiveSnapshotId])

  useEffect(() => {
    if (conversationId) {
      setActiveConversationId(conversationId)
      return
    }
    const storedId = loadAnonConversationId()
    if (storedId) {
      getConversationFetcher(storedId)
        .then(() => {
          saveAnonConversationId(storedId)
        })
        .catch(() => {
          localStorage.removeItem('cinepal_anon_conv_id')
        })
    }
  }, [conversationId, setActiveConversationId, loadAnonConversationId, saveAnonConversationId])

  const currentConversationId = conversationId ?? activeConversationId

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[var(--color-bg)]">
      <Header />

      <div className="flex flex-1 pt-14">
        <HistorySidebar />

        {!currentConversationId ? (
          <WelcomePage />
        ) : (
          <>
            {/* Left: scrollable chat (40%) */}
            <div className="flex flex-col basis-2/5 min-w-0 shrink-0 border-r border-[var(--color-border)] overflow-hidden">
              <ChatPanel conversationId={currentConversationId} />
            </div>

            {/* Right: snapshot panel (60%) */}
            <div className="basis-3/5 bg-[var(--color-surface)]">
              <ClusterSnapshotTab conversationId={currentConversationId} />
            </div>
          </>
        )}
      </div>

      {currentConversationId && <FloatingMascot />}
    </div>
  )
}
