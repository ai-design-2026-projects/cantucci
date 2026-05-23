import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { logoutFetcher } from '@/api/services/auth'
import { useAuthStore } from '@/store/useAuthStore'
import { Button } from '@/components/button'

/**
 * Displays the authenticated user's email and a log-out button.
 * On logout, clears auth state and any cached queries.
 *
 * @returns Inline user identity and logout controls.
 */
export function UserMenu() {
  const { user, setUser } = useAuthStore()
  const queryClient = useQueryClient()

  const { mutate } = useMutation({
    mutationFn: logoutFetcher,
    onSuccess: () => {
      setUser(null)
      queryClient.clear()
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
