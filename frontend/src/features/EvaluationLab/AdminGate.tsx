import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'

/**
 * Route guard for admin-only pages. While auth is hydrating shows a spinner;
 * once settled, redirects non-admins to / silently.
 */
export function AdminGate({ children }: { children: ReactNode }) {
    const { user, status } = useAuthStore()

    if (status === 'idle' || status === 'loading') {
        return (
            <div className="flex h-screen items-center justify-center">
                <div className="h-5 w-5 rounded-full border-2 border-[var(--color-primary)] border-t-transparent animate-spin" />
            </div>
        )
    }

    if (!user || user.role !== 'admin') {
        return <Navigate to="/" replace />
    }

    return <>{children}</>
}
