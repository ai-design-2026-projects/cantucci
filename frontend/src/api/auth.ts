import { apiClient } from './client'
import type { LoginResponse, User } from '@/lib/types'

/**
 * Authenticate an existing user and set the HttpOnly auth cookie.
 *
 * @param email    - User email address.
 * @param password - User password.
 * @returns LoginResponse with token and user object.
 */
export async function loginFetcher(email: string, password: string): Promise<LoginResponse> {
  return apiClient<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

/**
 * Register a new user account and set the HttpOnly auth cookie.
 *
 * @param email    - New user email address.
 * @param password - New user password (minimum 8 characters).
 * @returns LoginResponse with token and user object.
 */
export async function registerFetcher(email: string, password: string): Promise<LoginResponse> {
  return apiClient<LoginResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

/**
 * Clear the auth cookie to log out.
 *
 * @returns void
 */
export async function logoutFetcher(): Promise<void> {
  return apiClient<void>('/auth/logout', { method: 'POST' })
}

/**
 * Fetch the currently authenticated user from the session cookie.
 *
 * @returns User object or null when the request is anonymous / cookie expired.
 */
export async function meFetcher(): Promise<User | null> {
  try {
    return await apiClient<User>('/auth/me')
  } catch {
    return null
  }
}
