import { Link } from 'react-router-dom'
import { Mascot } from '@/components/mascot'
import { Button } from '@/components/button'

/**
 * Shown in the history drawer when the user is not authenticated.
 * Prompts them to sign in to access their conversation history.
 *
 * @returns Auth gate placeholder with Poppy and sign-in link.
 */
export function AuthGatePrompt() {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-4 px-6 text-center">
      <Mascot expression="sad" size="md" />
      <p className="text-sm font-medium text-[var(--color-text)]">
        Sign in to keep your conversations
      </p>
      <p className="text-xs text-[var(--color-muted)]">
        Anonymous chats are saved in your browser but lost when you clear the cache.
      </p>
      <Button asChild size="sm">
        <Link to="/login">Sign In</Link>
      </Button>
    </div>
  )
}
