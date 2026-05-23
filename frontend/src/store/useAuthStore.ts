import { create } from 'zustand'
import type { User } from '@/api/dto/auth'

type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'unauthenticated'

interface AuthState {
	user: User | null
	status: AuthStatus
	setUser: (user: User | null) => void
	setStatus: (status: AuthStatus) => void
}

/**
 * Global auth store. Status drives whether the app shows the auth gate.
 * Hydration is triggered once on app mount by calling useAuthStore.getState().hydrate()
 * via the useAuthHydration hook.
 */
export const useAuthStore = create<AuthState>((set) => ({
	user: null,
	status: 'idle',
	setUser: (user) => set({ user, status: user ? 'authenticated' : 'unauthenticated' }),
	setStatus: (status) => set({ status }),
}))
