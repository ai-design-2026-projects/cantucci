import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { createConversationFetcher } from '@/api/conversations'
import { useConversationStore } from '@/store/useConversationStore'
import { useAuthStore } from '@/store/useAuthStore'
import { Mascot } from '@/components/mascot'
import { StartButton } from './components/StartButton'

/**
 * Welcome screen shown when the user has no active conversation.
 * Creates a new conversation on click and navigates to the chat route.
 *
 * @returns Full-page welcome layout with Poppy mascot and start button.
 */
export function WelcomePage() {
  const navigate = useNavigate()
  const { saveAnonConversationId, setActiveConversationId } = useConversationStore()
  const user = useAuthStore((s) => s.user)

  const { mutate, isPending } = useMutation({
    mutationFn: createConversationFetcher,
    onSuccess: (conv) => {
      if (user) {
        setActiveConversationId(conv.id)
      } else {
        saveAnonConversationId(conv.id)
      }
      navigate(`/c/${conv.id}`)
    },
  })

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-10 px-8 bg-[var(--color-bg)]">
      <motion.div
        className="flex flex-col items-center gap-4"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <Mascot expression="happy" size="lg" />
        <h1 className="text-4xl font-display text-[var(--color-text)] text-center">
          Meet Poppy
        </h1>
        <p className="text-lg text-[var(--color-muted)] text-center max-w-md leading-relaxed">
          CinePal&apos;s AI clustering engine. Chat with Poppy to reorganize your movie catalogue — merge, split, and refine clusters through conversation.
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3, duration: 0.4 }}
      >
        <StartButton onClick={() => mutate()} isLoading={isPending} />
      </motion.div>
    </div>
  )
}
