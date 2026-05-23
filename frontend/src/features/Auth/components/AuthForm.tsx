import { useState } from 'react'
import { Button } from '@/components/button'
import { Input } from '@/components/input'
import { cn } from '@/lib/utils'

interface AuthFormProps {
  mode: 'login' | 'register'
  onSubmit: (email: string, password: string) => void
  isPending: boolean
  error: string | null
}

/**
 * Shared login/register form with inline validation.
 *
 * @param mode      - Controls heading text and submit label.
 * @param onSubmit  - Called with email and password when the form is valid.
 * @param isPending - Disables the form while the mutation is in flight.
 * @param error     - Server-side error message to display.
 * @returns Form element.
 */
export function AuthForm({ mode, onSubmit, isPending, error }: AuthFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({})

  function validate(): boolean {
    const errs: { email?: string; password?: string } = {}
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = 'Enter a valid email'
    if (!password || password.length < 8) errs.password = 'Password must be at least 8 characters'
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (validate()) onSubmit(email, password)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 w-full">
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-[var(--color-text)]" htmlFor="email">
          Email
        </label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          disabled={isPending}
          className={cn(fieldErrors.email && 'border-red-400')}
        />
        {fieldErrors.email && (
          <p className="text-xs text-red-500">{fieldErrors.email}</p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-[var(--color-text)]" htmlFor="password">
          Password
        </label>
        <Input
          id="password"
          type="password"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Min. 8 characters"
          disabled={isPending}
          className={cn(fieldErrors.password && 'border-red-400')}
        />
        {fieldErrors.password && (
          <p className="text-xs text-red-500">{fieldErrors.password}</p>
        )}
      </div>

      {error && (
        <p className="text-sm text-red-500 text-center">{error}</p>
      )}

      <Button type="submit" disabled={isPending} className="w-full mt-1">
        {isPending ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create Account'}
      </Button>
    </form>
  )
}
