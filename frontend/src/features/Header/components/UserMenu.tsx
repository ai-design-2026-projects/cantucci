import { Link } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { Button } from '@/components/button'
import { useUserMenu } from '../hooks/useUserMenu'

/**
 * Displays the authenticated user's email and a log-out button.
 * On logout, clears all store state, localStorage, and cached queries, then
 * navigates to the login page.
 *
 * @returns Inline user identity and logout controls.
 */
export function UserMenu() {
	const { user, logout } = useUserMenu()

	if (!user) {
		return (
			<Button asChild variant="outline" size="sm">
				<Link to="/login">Sign In</Link>
			</Button>
		)
	}

	return (
		<div className="flex items-center gap-2">
			<span className="text-sm text-[var(--color-muted)] hidden sm:inline">
				{user.email}
			</span>
			<Button variant="ghost" size="sm" onClick={logout} className="gap-1">
				<LogOut className="h-4 w-4" />
				<span className="hidden sm:inline">Log out</span>
			</Button>
		</div>
	)
}
