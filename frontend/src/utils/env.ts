/**
 * Type-safe access to Vite environment variables.
 *
 * @returns The VITE_API_BASE env var, defaulting to ``""`` (same origin via proxy).
 */
export function apiBase(): string {
  return import.meta.env.VITE_API_BASE ?? "";
}
