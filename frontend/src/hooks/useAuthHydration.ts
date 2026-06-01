import { useEffect } from 'react'
import { meFetcher } from '@/api/services/auth'
import { useAuthStore } from '@/store/useAuthStore'

/**
 * Triggers the /auth/me bootstrap exactly once per mount, only when
 * auth status is still 'idle'. Safe to call from multiple components —
 * the 'idle' guard prevents duplicate fetches if another component already
 * started hydration.
 */
export function useAuthHydration() {
    const { setUser, setStatus, status } = useAuthStore()

    useEffect(() => {
        if (status !== 'idle') return
        setStatus('loading')
        meFetcher().then((user) => setUser(user))
    }, [status, setUser, setStatus])
}
