import { useState } from 'react'

type SubmitAuth = (email: string, password: string) => void

interface AuthFieldErrors {
	email?: string
	password?: string
}

/**
 * Owns the auth form state, validation, and submit behavior.
 *
 * @param onSubmit - Called with valid email and password values.
 * @returns Form field state, errors, and event handlers.
 */
export function useAuthForm(onSubmit: SubmitAuth) {
	const [email, setEmail] = useState('')
	const [password, setPassword] = useState('')
	const [fieldErrors, setFieldErrors] = useState<AuthFieldErrors>({})

	function validate(): boolean {
		const errs: AuthFieldErrors = {}
		if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = 'Enter a valid email'
		if (!password || password.length < 8) errs.password = 'Password must be at least 8 characters'
		setFieldErrors(errs)
		return Object.keys(errs).length === 0
	}

	function handleSubmit(e: React.FormEvent) {
		e.preventDefault()
		if (validate()) onSubmit(email, password)
	}

	return {
		email,
		setEmail,
		password,
		setPassword,
		fieldErrors,
		handleSubmit,
	}
}