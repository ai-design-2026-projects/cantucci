import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { logoutFetcher } from '@/api/services/auth'
import { useAuthStore } from '@/store/useAuthStore'
import { useConversationStore } from '@/store/useConversationStore'
import { useSnapshotStore } from '@/store/useSnapshotStore'
import { Button } from '@/components/button'

/**
 * Displays the authenticated user's email and a log-out button.
 * On logout, clears all store state, localStorage, and cached queries, then
 * navigates to the login page.
 *
 * @returns Inline user identity and logout controls.
 */
export function UserMenu() {
  const { user, setUser } = useAuthStore()
  const { setActiveConversationId, clearAnonConversationId } = useConversationStore()
  const { setActiveSnapshotId } = useSnapshotStore()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { mutate } = useMutation({
    mutationFn: logoutFetcher,
    onSuccess: () => {
      setUser(null)
      setActiveConversationId(null)
      clearAnonConversationId()
      setActiveSnapshotId(null)
      queryClient.clear()
      navigate('/login')
    },
  })

  if (!user) return null

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-[var(--color-muted)] hidden sm:inline">
        {user.email}
      </span>
      <Button variant="ghost" size="sm" onClick={() => mutate()} className="gap-1">
        <LogOut className="h-4 w-4" />
        <span className="hidden sm:inline">Log out</span>
      </Button>
    </div>
  )
}

/**
 * Sign-in button shown when the user is unauthenticated.
 *
 * @returns Link-styled button to the login page.
 */
export function SignInButton() {
  return (
    <Button asChild variant="outline" size="sm">
      <Link to="/login">Sign In</Link>
    </Button>
  )
}
