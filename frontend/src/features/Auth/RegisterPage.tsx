import { Link } from 'react-router-dom'
import { Mascot } from '@/components/mascot'
import { AuthForm } from './components/AuthForm'
import { useRegister } from './hooks/useRegister'

/**
 * Register page. Mirrors LoginPage structure with register mode.
 *
 * @returns Full-page register layout.
 */
export function RegisterPage() {
	const { mutate, isPending, error } = useRegister()

	return (
		<div className="min-h-screen flex items-center justify-center bg-[var(--color-bg)] px-4">
			<div className="w-full max-w-sm flex flex-col items-center gap-8">
				<Link to="/" className="text-sm text-[var(--color-muted)] hover:text-[var(--color-text)] self-start">
					← Back to CinePal
				</Link>

				<div className="flex flex-col items-center gap-3">
					<Mascot expression="excited" size="lg" />
					<h1 className="text-3xl font-display text-[var(--color-text)]">Join CinePal</h1>
					<p className="text-sm text-[var(--color-muted)]">Create an account to save your conversations</p>
				</div>

				<div className="w-full bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-6">
					<AuthForm
						mode="register"
						onSubmit={(email, password) => mutate({ email, password })}
						isPending={isPending}
						error={error ? error.message : null}
					/>
					<p className="text-sm text-center text-[var(--color-muted)] mt-4">
						Already have an account?{' '}
						<Link to="/login" className="text-[var(--color-primary)] hover:underline">
							Sign in
						</Link>
					</p>
				</div>
			</div>
		</div>
	)
}
