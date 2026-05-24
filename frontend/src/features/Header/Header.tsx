import { BrandMark } from './components/BrandMark'
import { ThemeToggle } from './components/ThemeToggle'
import { UserMenu } from './components/UserMenu'

/**
 * Fixed top header. Contains the brand mark, theme toggle, and auth controls.
 *
 * @returns Fixed-position full-width header bar.
 */
export function Header() {
	return (
		<header className="fixed top-0 left-0 right-0 z-30 h-14 flex items-center justify-between px-4 bg-[var(--color-surface)] border-b border-[var(--color-border)]">
			<BrandMark />

			<div className="flex items-center gap-1">
				<ThemeToggle />
				<UserMenu />
			</div>
		</header>
	)
}
