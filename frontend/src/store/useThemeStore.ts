import { create } from 'zustand'
import { THEME_KEY } from '@/lib/constants'

type Theme = 'light' | 'dark'

interface ThemeState {
	theme: Theme
	toggleTheme: () => void
	initTheme: () => void
}

function applyTheme(theme: Theme): void {
	document.documentElement.setAttribute('data-theme', theme)
}

/**
 * Manages light/dark theme. Persists selection in localStorage.
 * initTheme() should be called once on app mount before the first render.
 */
export const useThemeStore = create<ThemeState>((set, get) => ({
	theme: 'light',

	toggleTheme: () => {
		const next: Theme = get().theme === 'light' ? 'dark' : 'light'
		localStorage.setItem(THEME_KEY, next)
		applyTheme(next)
		set({ theme: next })
	},

	initTheme: () => {
		const stored = localStorage.getItem(THEME_KEY) as Theme | null
		const theme = stored ?? 'light'
		applyTheme(theme)
		set({ theme })
	},
}))
