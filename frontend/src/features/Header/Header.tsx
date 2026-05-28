import { Link, useLocation } from 'react-router-dom'
import { FlaskConical, LayoutDashboard } from 'lucide-react'
import { BrandMark } from './components/BrandMark'
import { ThemeToggle } from './components/ThemeToggle'
import { UserMenu } from './components/UserMenu'
import { Button } from '@/components/button'
import { useAuthStore } from '@/store/useAuthStore'

/**
 * Fixed top header. Contains the brand mark, theme toggle, and auth controls.
 * Admin users see an Eval Lab button that toggles between /eval-lab and /.
 *
 * @returns Fixed-position full-width header bar.
 */
export function Header() {
	const isAdmin = useAuthStore((s) => s.user?.role === 'admin')
	const { pathname } = useLocation()
	const inEvalLab = pathname === '/eval-lab'

	return (
		<header className="fixed top-0 left-0 right-0 z-30 h-14 flex items-center justify-between px-4 bg-[var(--color-surface)] border-b border-[var(--color-border)]">
			<BrandMark />

			<div className="flex items-center gap-1">
				{isAdmin && (
					<Button asChild variant="ghost" size="sm" className="gap-1.5 text-xs">
						<Link to={inEvalLab ? '/' : '/eval-lab'}>
							{inEvalLab ? (
								<><LayoutDashboard className="h-3.5 w-3.5" /> App</>
							) : (
								<><FlaskConical className="h-3.5 w-3.5" /> Eval Lab</>
							)}
						</Link>
					</Button>
				)}
				<ThemeToggle />
				<UserMenu />
			</div>
		</header>
	)
}
