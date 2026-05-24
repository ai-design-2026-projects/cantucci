import { Sun, Moon } from 'lucide-react'
import { Button } from '@/components/button'
import { useThemeStore } from '@/store/useThemeStore'

/**
 * Sun/moon toggle button for switching between light and dark themes.
 *
 * @returns Icon button that flips the active theme.
 */
export function ThemeToggle() {
	const { theme, toggleTheme } = useThemeStore()

	return (
		<Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
			{theme === 'light' ? (
				<Moon className="h-4 w-4" />
			) : (
				<Sun className="h-4 w-4" />
			)}
		</Button>
	)
}
