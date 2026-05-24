import { Link } from 'react-router-dom'
import { Mascot } from '@/components/mascot'
import { AuthForm } from './components/AuthForm'
import { useLogin } from './hooks/useLogin'

/**
 * Login page. Renders the Poppy mascot, the auth form, and links to register
 * and back to the main app.
 *
 * @returns Full-page login layout.
 */
export function LoginPage() {
	const { mutate, isPending, error } = useLogin()

	return (
		<div className="min-h-screen flex items-center justify-center bg-[var(--color-bg)] px-4">
			<div className="w-full max-w-sm flex flex-col items-center gap-8">
				<Link to="/" className="text-sm text-[var(--color-muted)] hover:text-[var(--color-text)] self-start">
					← Back to CinePal
				</Link>

				<div className="flex flex-col items-center gap-3">
					<Mascot expression="happy" size="lg" />
					<h1 className="text-3xl font-display text-[var(--color-text)]">Welcome back</h1>
					<p className="text-sm text-[var(--color-muted)]">Sign in to access your conversation history</p>
				</div>

				<div className="w-full bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-6">
					<AuthForm
						mode="login"
						onSubmit={(email, password) => mutate({ email, password })}
						isPending={isPending}
						error={error ? error.message : null}
					/>
					<p className="text-sm text-center text-[var(--color-muted)] mt-4">
						Don&apos;t have an account?{' '}
						<Link to="/register" className="text-[var(--color-primary)] hover:underline">
							Sign up
						</Link>
					</p>
				</div>
			</div>
		</div>
	)
}
