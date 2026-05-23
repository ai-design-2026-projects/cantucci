import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuthStore } from './store/useAuthStore'
import { useThemeStore } from './store/useThemeStore'
import { useConversationStore } from './store/useConversationStore'
import { meFetcher } from './api/services/auth'
import { getConversationFetcher } from './api/services/conversations'
import { Header } from './features/Header/Header'
import { ChatPanel } from './features/Chat/ChatPanel'
import { ClusterSnapshotTab } from './features/ClusterSnapshotTab/ClusterSnapshotTab'
import { WelcomePage } from './features/Welcome/WelcomePage'
import { HistorySidebar } from './features/History/HistorySidebar'

/**
 * Root application layout. Handles auth hydration, theme init, and anonymous
 * conversation restoration. Always renders the two-column layout — left panel
 * shows the welcome screen or chat; right panel shows the scatter plot (grey
 * silhouette when no conversation is active, colored clusters when one is).
 *
 * @returns Application shell.
 */
export default function App() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()

  const { setUser, setStatus } = useAuthStore()
  const { initTheme } = useThemeStore()
  const { setActiveConversationId, loadAnonConversationId, saveAnonConversationId, clearAnonConversationId } = useConversationStore()

  useEffect(() => {
    initTheme()
  }, [initTheme])

  useEffect(() => {
    setStatus('loading')
    meFetcher().then((user) => setUser(user))
  }, [setUser, setStatus])

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
          navigate(`/c/${storedId}`, { replace: true })
        })
        .catch(() => {
          clearAnonConversationId()
        })
    }
  }, [conversationId, setActiveConversationId, loadAnonConversationId, saveAnonConversationId, clearAnonConversationId, navigate])

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[var(--color-bg)]">
      <Header />

      <div className="flex flex-1 min-h-0 pt-14">
        <HistorySidebar />

        {/* Left: chat or welcome (40%) */}
        <div className="flex flex-col basis-2/5 min-w-0 shrink-0 min-h-0 border-r border-[var(--color-border)] overflow-hidden">
          {conversationId ? (
            <ChatPanel conversationId={conversationId} />
          ) : (
            <WelcomePage />
          )}
        </div>

        {/* Right: snapshot scatter plot (60%) — always visible */}
        <div className="basis-3/5 bg-[var(--color-surface)] overflow-hidden">
          <ClusterSnapshotTab conversationId={conversationId} />
        </div>
      </div>
    </div>
  )
}
