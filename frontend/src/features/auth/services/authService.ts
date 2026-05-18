import { get, post, ApiError } from "@/clients/apiClient";
import type { LoginResponse, User } from "@/utils/types";

/**
 * Log in with email and password.
 *
 * @param email    User email.
 * @param password Plaintext password.
 * @returns Authenticated User on success.
 * @throws ApiError on invalid credentials, validation errors, or network failure.
 */
export async function login(email: string, password: string): Promise<User> {
  const data = await post<LoginResponse>("/auth/login", { email, password });
  return data.user;
}

/**
 * Register a new account and immediately authenticate.
 *
 * @param email    User email.
 * @param password Plaintext password (min 8 chars enforced by the backend).
 * @returns Authenticated User on success.
 * @throws ApiError on duplicate email, validation errors, or network failure.
 */
export async function register(email: string, password: string): Promise<User> {
  const data = await post<LoginResponse>("/auth/register", { email, password });
  return data.user;
}

/**
 * Clear the auth_token cookie server-side, logging the user out.
 *
 * @throws ApiError on network failure.
 */
export async function logout(): Promise<void> {
  await post<void>("/auth/logout", {});
}

/**
 * Fetch the currently authenticated user from the server.
 *
 * Marks the request as a bootstrap call so a 401 does not trigger the global
 * on401 handler — anonymous visits are expected and silently return null.
 *
 * @returns Authenticated User, or null if the session cookie is absent or expired.
 */
export async function fetchMe(): Promise<User | null> {
  try {
    return await get<User>("/auth/me", true);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      return null;
    }
    throw err;
  }
}
